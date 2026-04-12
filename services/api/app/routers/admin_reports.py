"""Admin reports — CSV export endpoints for 6 report types."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import (
    AdminAuditLog,
    AdminUser,
    Employee,
    Product,
    StockMovement,
    Supplier,
    Transaction,
    TransactionLine,
)

router = APIRouter(prefix="/v1/admin/reports", tags=["Admin Reports"])

REPORT_IDS = {"sales", "inventory", "movements", "suppliers", "staff", "audit"}


def _require_tenant(ctx):
    if ctx.is_legacy_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Legacy token not allowed")
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant required")
    return ctx.tenant_id


def _csv_response(rows: list[list], headers: list[str], filename: str) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    writer.writerows(rows)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _ts() -> str:
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


@router.get("/export", dependencies=[require_permission("reports:read")])
def export_report(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    report: str = Query(...),
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
) -> StreamingResponse:
    if report not in REPORT_IDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown report '{report}'. Must be one of: {', '.join(sorted(REPORT_IDS))}",
        )
    tenant_id = _require_tenant(ctx)

    if report == "sales":
        return _export_sales(db, tenant_id, from_date, to_date)
    if report == "inventory":
        return _export_inventory(db, tenant_id)
    if report == "movements":
        return _export_movements(db, tenant_id, from_date, to_date)
    if report == "suppliers":
        return _export_suppliers(db, tenant_id)
    if report == "staff":
        return _export_staff(db, tenant_id)
    if report == "audit":
        return _export_audit(db, tenant_id, from_date, to_date)
    raise HTTPException(status_code=500, detail="Unhandled report type")


# ---------------------------------------------------------------------------
# Individual exporters
# ---------------------------------------------------------------------------


def _export_sales(db: Session, tenant_id, from_date, to_date) -> StreamingResponse:
    stmt = (
        select(Transaction)
        .where(Transaction.tenant_id == tenant_id)
        .order_by(Transaction.created_at.desc())
    )
    if from_date:
        stmt = stmt.where(Transaction.created_at >= from_date)
    if to_date:
        stmt = stmt.where(Transaction.created_at <= to_date + "T23:59:59")

    txns = db.execute(stmt).scalars().all()
    headers = ["id", "created_at", "kind", "status", "total_cents", "tax_cents", "shop_id"]
    rows = [
        [
            str(t.id),
            t.created_at.isoformat(),
            t.kind,
            t.status,
            t.total_cents,
            t.tax_cents,
            str(t.shop_id) if t.shop_id else "",
        ]
        for t in txns
    ]
    return _csv_response(rows, headers, f"sales_{_ts()}.csv")


def _export_inventory(db: Session, tenant_id) -> StreamingResponse:
    products = db.execute(
        select(Product)
        .where(Product.tenant_id == tenant_id, Product.status == "active")
        .order_by(Product.name)
    ).scalars().all()

    # Aggregate stock across all shops per product in a single query
    stock_rows = db.execute(
        select(
            StockMovement.product_id,
            func.coalesce(func.sum(StockMovement.quantity_delta), 0).label("qty"),
        )
        .where(StockMovement.tenant_id == tenant_id)
        .group_by(StockMovement.product_id)
    ).all()
    stock_by_product: dict = {str(r.product_id): int(r.qty) for r in stock_rows}

    headers = ["sku", "name", "category", "unit_price_cents", "reorder_point", "current_stock", "extended_value_cents"]
    rows = []
    for p in products:
        qty = stock_by_product.get(str(p.id), 0)
        rows.append([
            p.sku,
            p.name,
            p.category or "",
            p.unit_price_cents,
            p.reorder_point,
            qty,
            qty * p.unit_price_cents,
        ])
    return _csv_response(rows, headers, f"inventory_{_ts()}.csv")


def _export_movements(db: Session, tenant_id, from_date, to_date) -> StreamingResponse:
    stmt = (
        select(StockMovement)
        .where(StockMovement.tenant_id == tenant_id)
        .order_by(StockMovement.created_at.desc())
    )
    if from_date:
        stmt = stmt.where(StockMovement.created_at >= from_date)
    if to_date:
        stmt = stmt.where(StockMovement.created_at <= to_date + "T23:59:59")

    moves = db.execute(stmt).scalars().all()
    headers = ["id", "created_at", "product_id", "shop_id", "movement_type", "quantity_delta", "transaction_id", "idempotency_key"]
    rows = [
        [
            str(m.id),
            m.created_at.isoformat(),
            str(m.product_id),
            str(m.shop_id),
            m.movement_type,
            m.quantity_delta,
            str(m.transaction_id) if m.transaction_id else "",
            m.idempotency_key,
        ]
        for m in moves
    ]
    return _csv_response(rows, headers, f"movements_{_ts()}.csv")


def _export_suppliers(db: Session, tenant_id) -> StreamingResponse:
    suppliers = db.execute(
        select(Supplier)
        .where(Supplier.tenant_id == tenant_id)
        .order_by(Supplier.name)
    ).scalars().all()

    # Count POs per supplier
    from app.models import PurchaseOrder
    from sqlalchemy import func
    po_counts = dict(
        db.execute(
            select(PurchaseOrder.supplier_id, func.count(PurchaseOrder.id))
            .where(PurchaseOrder.tenant_id == tenant_id)
            .group_by(PurchaseOrder.supplier_id)
        ).all()
    )

    headers = ["id", "name", "status", "contact_email", "contact_phone", "total_purchase_orders", "created_at"]
    rows = [
        [
            str(s.id),
            s.name,
            s.status,
            s.contact_email or "",
            s.contact_phone or "",
            po_counts.get(s.id, 0),
            s.created_at.isoformat() if s.created_at else "",
        ]
        for s in suppliers
    ]
    return _csv_response(rows, headers, f"suppliers_{_ts()}.csv")


def _export_staff(db: Session, tenant_id) -> StreamingResponse:
    members = db.execute(
        select(Employee)
        .where(Employee.tenant_id == tenant_id)
        .order_by(Employee.name)
    ).scalars().all()

    headers = ["id", "name", "email", "position", "is_active", "created_at"]
    rows = [
        [
            str(m.id),
            m.name,
            m.email,
            m.position,
            m.is_active,
            m.created_at.isoformat() if m.created_at else "",
        ]
        for m in members
    ]
    return _csv_response(rows, headers, f"staff_{_ts()}.csv")


def _export_audit(db: Session, tenant_id, from_date, to_date) -> StreamingResponse:
    stmt = (
        select(AdminAuditLog)
        .where(AdminAuditLog.tenant_id == tenant_id)
        .order_by(AdminAuditLog.created_at.desc())
        .limit(10000)
    )
    if from_date:
        stmt = stmt.where(AdminAuditLog.created_at >= from_date)
    if to_date:
        stmt = stmt.where(AdminAuditLog.created_at <= to_date + "T23:59:59")

    logs = db.execute(stmt).scalars().all()

    op_ids = {r.operator_id for r in logs if r.operator_id}
    op_emails: dict = {}
    if op_ids:
        ops = db.execute(select(AdminUser).where(AdminUser.id.in_(op_ids))).scalars().all()
        op_emails = {o.id: o.email for o in ops}

    headers = ["id", "created_at", "actor", "action", "resource_type", "resource_id", "ip_address"]
    rows = [
        [
            str(r.id),
            r.created_at.isoformat(),
            op_emails.get(r.operator_id, "system") if r.operator_id else "system",
            r.action,
            r.resource_type,
            r.resource_id or "",
            r.ip_address or "",
        ]
        for r in logs
    ]
    return _csv_response(rows, headers, f"audit_{_ts()}.csv")
