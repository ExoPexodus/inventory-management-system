"""Admin console endpoints for the web dashboard (operator JWT or legacy admin token)."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Select, func, or_, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

import bcrypt

from app.auth.admin_deps import AdminAuthDep, AdminContext, require_permission
from app.db.admin_deps_db import get_db_admin
from app.services.audit_service import write_audit
from app.models import (
    Product,
    ProductGroup,
    PurchaseOrder,
    Role,
    Shop,
    StockAdjustment,
    StockMovement,
    Supplier,
    Transaction,
    TransactionLine,
    User,
)
from app.routers.transactions import (
    PaymentOut,
    TransactionListResponse,
    TransactionOut,
    _decode_cursor,
    _encode_cursor,
    _line_dto,
    _parse_status_filter,
    _product_labels_for_lines,
)
from app.services.stock import current_quantity

router = APIRouter(prefix="/v1/admin", tags=["Admin Console"])


def _require_operator_tenant(ctx: AdminContext) -> UUID:
    if ctx.is_legacy_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Legacy admin token is not allowed for this endpoint",
        )
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator is not assigned to a tenant",
        )
    return ctx.tenant_id


def _coerce_tenant_scope(ctx: AdminContext, requested_tenant_id: UUID | None) -> UUID:
    operator_tenant = _require_operator_tenant(ctx)
    if requested_tenant_id is not None and requested_tenant_id != operator_tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-tenant access is forbidden",
        )
    return operator_tenant


def _admin_transactions_base_stmt(
    tenant_id: UUID | None,
    shop_id: UUID | None,
    statuses: list[str] | None,
    search: str | None,
) -> Select:
    stmt = select(Transaction).options(
        selectinload(Transaction.lines),
        selectinload(Transaction.payments),
    )
    if tenant_id is not None:
        stmt = stmt.where(Transaction.tenant_id == tenant_id)
    if shop_id is not None:
        stmt = stmt.where(Transaction.shop_id == shop_id)
    if statuses:
        stmt = stmt.where(Transaction.status.in_(statuses))
    if search and search.strip():
        needle = f"%{search.strip()}%"
        matching = (
            select(TransactionLine.transaction_id)
            .join(Product, Product.id == TransactionLine.product_id)
            .where(or_(Product.name.ilike(needle), Product.sku.ilike(needle)))
            .distinct()
        )
        stmt = stmt.where(Transaction.id.in_(matching))
    return stmt


@router.get("/transactions", response_model=TransactionListResponse, dependencies=[require_permission("sales:read")])
def admin_list_transactions(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    tenant_id: UUID | None = None,
    shop_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
    status: str | None = Query(
        default=None,
        description="Comma-separated: posted,refunded,pending",
    ),
    q: str | None = Query(default=None, description="Filter by line product name or SKU (substring)."),
) -> TransactionListResponse:
    tenant_id = _coerce_tenant_scope(ctx, tenant_id)
    statuses = _parse_status_filter(status)
    stmt = _admin_transactions_base_stmt(tenant_id, shop_id, statuses=statuses, search=q)
    stmt = stmt.order_by(Transaction.created_at.desc(), Transaction.id.desc())

    if cursor:
        c_at, c_id = _decode_cursor(cursor)
        stmt = stmt.where(tuple_(Transaction.created_at, Transaction.id) < tuple_(c_at, c_id))

    stmt = stmt.limit(limit + 1)
    rows = list(db.execute(stmt).scalars().unique().all())

    next_cur: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cur = _encode_cursor(last.created_at, last.id)

    labels = _product_labels_for_lines(db, rows)

    # Build user name lookup for all referenced user IDs (cashiers)
    user_ids = {t.user_id for t in rows if t.user_id is not None}
    user_names: dict[UUID, str] = {}
    if user_ids:
        users = db.execute(select(User).where(User.id.in_(user_ids))).scalars().all()
        user_names = {u.id: u.name for u in users}

    items: list[TransactionOut] = []
    for t in rows:
        items.append(
            TransactionOut(
                id=t.id,
                shop_id=t.shop_id,
                kind=t.kind,
                status=t.status,
                total_cents=t.total_cents,
                tax_cents=t.tax_cents,
                client_mutation_id=t.client_mutation_id,
                created_at=t.created_at,
                lines=[_line_dto(ln, labels) for ln in t.lines],
                payments=[
                    PaymentOut(tender_type=p.tender_type, amount_cents=p.amount_cents) for p in t.payments
                ],
                cashier_name=user_names.get(t.user_id) if t.user_id else None,
            )
        )
    return TransactionListResponse(items=items, next_cursor=next_cur)


_VALID_TX_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"posted", "voided"},
    "flagged": {"posted", "voided"},
}


class TxStatusPatch(BaseModel):
    status: str


@router.patch("/transactions/{tx_id}/status", dependencies=[require_permission("sales:write")])
def patch_transaction_status(
    tx_id: UUID,
    body: TxStatusPatch,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> dict:
    tenant_id = _require_operator_tenant(ctx)
    tx = db.get(Transaction, tx_id)
    if tx is None or tx.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    allowed = _VALID_TX_STATUS_TRANSITIONS.get(tx.status, set())
    if body.status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot transition from '{tx.status}' to '{body.status}'. Allowed: {sorted(allowed) or 'none'}",
        )
    old_status = tx.status
    tx.status = body.status
    write_audit(
        db,
        tenant_id=tenant_id,
        operator_id=ctx.operator_id,
        action="update_transaction_status",
        resource_type="transaction",
        resource_id=str(tx_id),
        before={"status": old_status},
        after={"status": body.status},
    )
    db.commit()
    return {"id": str(tx_id), "status": body.status}


def _stock_alert_qty(db: Session, tenant_id: UUID | None, threshold: int) -> int:
    if tenant_id is None:
        return 0
    sub = (
        select(
            StockMovement.shop_id,
            StockMovement.product_id,
            func.coalesce(func.sum(StockMovement.quantity_delta), 0).label("qty"),
        )
        .join(Product, Product.id == StockMovement.product_id)
        .where(StockMovement.tenant_id == tenant_id, Product.active.is_(True))
        .group_by(StockMovement.shop_id, StockMovement.product_id)
        .having(func.coalesce(func.sum(StockMovement.quantity_delta), 0) <= threshold)
        .subquery()
    )
    return int(db.execute(select(func.count()).select_from(sub)).scalar_one())


def _stock_alert_qty_per_product(db: Session, tenant_id: UUID | None) -> int:
    """Count shop×product pairs where total stock ≤ product's own reorder_point."""
    if tenant_id is None:
        return 0
    reorder = Product.reorder_point
    sub = (
        select(
            StockMovement.shop_id,
            StockMovement.product_id,
            reorder.label("rp"),
        )
        .join(Product, Product.id == StockMovement.product_id)
        .where(StockMovement.tenant_id == tenant_id, Product.active.is_(True))
        .group_by(StockMovement.shop_id, StockMovement.product_id, reorder)
        .having(func.coalesce(func.sum(StockMovement.quantity_delta), 0) <= reorder)
        .subquery()
    )
    return int(db.execute(select(func.count()).select_from(sub)).scalar_one())


class RecentActivityItem(BaseModel):
    kind: str
    ref_id: UUID
    created_at: str
    detail: str


class DashboardSummaryOut(BaseModel):
    posted_transaction_count: int
    gross_sales_cents: int
    stock_alert_count: int
    supplier_count: int
    shop_count: int
    product_count: int
    tenant_count: int
    avg_transaction_cents: int = 0
    pending_order_count: int = 0
    revenue_delta_pct: float = 0.0
    recent_activity: list[RecentActivityItem]


@router.get("/dashboard-summary", response_model=DashboardSummaryOut, dependencies=[require_permission("analytics:read")])
def dashboard_summary(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    tenant_id: UUID | None = None,
    stock_alert_threshold: int = Query(default=5, ge=0, le=1_000_000),
    activity_limit: int = Query(default=12, ge=1, le=50),
) -> DashboardSummaryOut:
    tenant_id = _coerce_tenant_scope(ctx, tenant_id)
    txn_filters = [Transaction.status == "posted"]
    txn_filters.append(Transaction.tenant_id == tenant_id)

    posted_transaction_count = int(
        db.execute(select(func.count()).select_from(Transaction).where(*txn_filters)).scalar_one()
    )
    gross_sales_cents = int(
        db.execute(
            select(func.coalesce(func.sum(Transaction.total_cents), 0)).where(*txn_filters)
        ).scalar_one()
    )

    def count_model(model, tenant_col) -> int:
        c = select(func.count()).select_from(model)
        c = c.where(tenant_col == tenant_id)
        return int(db.execute(c).scalar_one())

    shop_count = count_model(Shop, Shop.tenant_id)
    product_count = count_model(Product, Product.tenant_id)
    supplier_count = count_model(Supplier, Supplier.tenant_id)
    tenant_count = 1

    stock_alert_count = _stock_alert_qty_per_product(db, tenant_id)

    avg_transaction_cents = (
        gross_sales_cents // posted_transaction_count if posted_transaction_count > 0 else 0
    )

    pending_order_count = int(
        db.execute(
            select(func.count())
            .select_from(PurchaseOrder)
            .where(PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.status == "ordered")
        ).scalar_one()
    )

    now = datetime.now(UTC)
    period_start = now - timedelta(days=30)
    prev_start = now - timedelta(days=60)
    curr_rev = int(
        db.execute(
            select(func.coalesce(func.sum(Transaction.total_cents), 0)).where(
                Transaction.tenant_id == tenant_id,
                Transaction.status == "posted",
                Transaction.created_at >= period_start,
            )
        ).scalar_one()
    )
    prev_rev = int(
        db.execute(
            select(func.coalesce(func.sum(Transaction.total_cents), 0)).where(
                Transaction.tenant_id == tenant_id,
                Transaction.status == "posted",
                Transaction.created_at >= prev_start,
                Transaction.created_at < period_start,
            )
        ).scalar_one()
    )
    revenue_delta_pct = round((curr_rev - prev_rev) / prev_rev * 100, 1) if prev_rev > 0 else 0.0

    txns = db.execute(
        select(Transaction)
        .where(*txn_filters)
        .order_by(Transaction.created_at.desc())
        .limit(activity_limit)
    ).scalars().all()
    move_stmt = select(StockMovement).order_by(StockMovement.created_at.desc()).limit(activity_limit)
    move_stmt = move_stmt.where(StockMovement.tenant_id == tenant_id)
    moves = db.execute(move_stmt).scalars().all()

    items: list[RecentActivityItem] = []
    for t in txns:
        items.append(
            RecentActivityItem(
                kind="sale",
                ref_id=t.id,
                created_at=t.created_at.isoformat(),
                detail=f"${t.total_cents / 100:.2f} · {t.kind}",
            )
        )
    for m in moves:
        items.append(
            RecentActivityItem(
                kind="adjustment",
                ref_id=m.id,
                created_at=m.created_at.isoformat(),
                detail=f"\u0394{m.quantity_delta:+d} · {m.movement_type}",
            )
        )
    items.sort(key=lambda x: x.created_at, reverse=True)
    items = items[:activity_limit]

    return DashboardSummaryOut(
        posted_transaction_count=posted_transaction_count,
        gross_sales_cents=gross_sales_cents,
        stock_alert_count=stock_alert_count,
        supplier_count=supplier_count,
        shop_count=shop_count,
        product_count=product_count,
        tenant_count=tenant_count,
        avg_transaction_cents=avg_transaction_cents,
        pending_order_count=pending_order_count,
        revenue_delta_pct=revenue_delta_pct,
        recent_activity=items,
    )


class SalesSeriesPoint(BaseModel):
    day: str
    gross_cents: int
    transaction_count: int


class SalesSeriesResponse(BaseModel):
    points: list[SalesSeriesPoint]


@router.get("/analytics/sales-series", response_model=SalesSeriesResponse, dependencies=[require_permission("analytics:read")])
def sales_series(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    tenant_id: UUID | None = None,
    days: int = Query(default=30, ge=1, le=366),
) -> SalesSeriesResponse:
    tenant_id = _coerce_tenant_scope(ctx, tenant_id)
    start = datetime.now(UTC) - timedelta(days=days)
    day_bucket = func.date_trunc("day", Transaction.created_at).label("day")
    stmt = (
        select(
            day_bucket,
            func.coalesce(func.sum(Transaction.total_cents), 0).label("gross"),
            func.count(Transaction.id).label("cnt"),
        )
        .where(Transaction.status == "posted", Transaction.created_at >= start)
    )
    stmt = stmt.where(Transaction.tenant_id == tenant_id)
    stmt = stmt.group_by(day_bucket).order_by(day_bucket)
    rows = db.execute(stmt).all()
    points: list[SalesSeriesPoint] = []
    for r in rows:
        d = r.day
        if isinstance(d, datetime):
            day_str = d.date().isoformat()
        elif hasattr(d, "isoformat"):
            day_str = d.isoformat()[:10]
        else:
            day_str = str(d)[:10]
        points.append(
            SalesSeriesPoint(
                day=day_str,
                gross_cents=int(r.gross),
                transaction_count=int(r.cnt),
            )
        )
    return SalesSeriesResponse(points=points)


class SupplierOut(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    status: str
    contact_email: str | None
    contact_phone: str | None
    notes: str | None
    created_at: datetime


class CreateSupplierBody(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    status: str = Field(default="active", max_length=32)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None, max_length=64)
    notes: str | None = None


class PatchSupplierBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = Field(default=None, max_length=32)
    contact_email: str | None = None
    contact_phone: str | None = Field(default=None, max_length=64)
    notes: str | None = None


@router.get("/suppliers", response_model=list[SupplierOut], dependencies=[require_permission("procurement:read")])
def list_suppliers(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    tenant_id: UUID | None = None,
) -> list[SupplierOut]:
    tenant_id = _coerce_tenant_scope(ctx, tenant_id)
    stmt = select(Supplier).order_by(Supplier.created_at.desc())
    stmt = stmt.where(Supplier.tenant_id == tenant_id)
    rows = db.execute(stmt).scalars().all()
    return [
        SupplierOut(
            id=r.id,
            tenant_id=r.tenant_id,
            name=r.name,
            status=r.status,
            contact_email=r.contact_email,
            contact_phone=r.contact_phone,
            notes=r.notes,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/suppliers", response_model=SupplierOut, dependencies=[require_permission("procurement:write")])
def create_supplier(
    body: CreateSupplierBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> SupplierOut:
    tenant_id = _require_operator_tenant(ctx)
    row = Supplier(
        tenant_id=tenant_id,
        name=body.name.strip(),
        status=body.status.strip().lower(),
        contact_email=body.contact_email,
        contact_phone=body.contact_phone,
        notes=body.notes,
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        tenant_id=tenant_id,
        operator_id=ctx.operator_id,
        action="create_supplier",
        resource_type="supplier",
        resource_id=str(row.id),
        after={"name": row.name, "status": row.status},
    )
    db.commit()
    db.refresh(row)
    return SupplierOut(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        status=row.status,
        contact_email=row.contact_email,
        contact_phone=row.contact_phone,
        notes=row.notes,
        created_at=row.created_at,
    )


@router.patch("/suppliers/{supplier_id}", response_model=SupplierOut, dependencies=[require_permission("procurement:write")])
def patch_supplier(
    supplier_id: UUID,
    body: PatchSupplierBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> SupplierOut:
    tenant_id = _require_operator_tenant(ctx)
    row = db.get(Supplier, supplier_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    if row.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access is forbidden")
    before_snap = {"name": row.name, "status": row.status}
    if body.name is not None:
        row.name = body.name.strip()
    if body.status is not None:
        row.status = body.status.strip().lower()
    if body.contact_email is not None:
        row.contact_email = body.contact_email
    if body.contact_phone is not None:
        row.contact_phone = body.contact_phone
    if body.notes is not None:
        row.notes = body.notes
    write_audit(
        db,
        tenant_id=tenant_id,
        operator_id=ctx.operator_id,
        action="update_supplier",
        resource_type="supplier",
        resource_id=str(supplier_id),
        before=before_snap,
        after={"name": row.name, "status": row.status},
    )
    db.commit()
    db.refresh(row)
    return SupplierOut(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        status=row.status,
        contact_email=row.contact_email,
        contact_phone=row.contact_phone,
        notes=row.notes,
        created_at=row.created_at,
    )


def _movement_encode_cursor(created_at: datetime, mid: UUID) -> str:
    payload = f"{created_at.isoformat()}|{mid}"
    raw = base64.urlsafe_b64encode(payload.encode())
    return raw.decode().rstrip("=")


def _movement_decode_cursor(cur: str) -> tuple[datetime, UUID]:
    pad = "=" * (-len(cur) % 4)
    try:
        decoded = base64.urlsafe_b64decode(cur + pad).decode()
        ts, sid = decoded.split("|", 1)
        return datetime.fromisoformat(ts), UUID(sid)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid_cursor",
        ) from exc


class StockMovementOut(BaseModel):
    id: UUID
    tenant_id: UUID
    shop_id: UUID
    shop_name: str | None = None
    product_id: UUID
    product_sku: str | None = None
    product_name: str | None = None
    quantity_delta: int
    movement_type: str
    transaction_id: UUID | None
    created_at: datetime


class StockMovementListResponse(BaseModel):
    items: list[StockMovementOut]
    next_cursor: str | None = None


@router.get("/inventory/movements", response_model=StockMovementListResponse, dependencies=[require_permission("inventory:read")])
def list_stock_movements(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    tenant_id: UUID | None = None,
    shop_id: UUID | None = None,
    product_id: UUID | None = None,
    movement_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
) -> StockMovementListResponse:
    tenant_id = _coerce_tenant_scope(ctx, tenant_id)
    stmt = select(StockMovement).order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
    stmt = stmt.where(StockMovement.tenant_id == tenant_id)
    if shop_id is not None:
        stmt = stmt.where(StockMovement.shop_id == shop_id)
    if product_id is not None:
        stmt = stmt.where(StockMovement.product_id == product_id)
    if movement_type is not None and movement_type.strip():
        stmt = stmt.where(StockMovement.movement_type == movement_type.strip())

    if cursor:
        c_at, c_id = _movement_decode_cursor(cursor)
        stmt = stmt.where(tuple_(StockMovement.created_at, StockMovement.id) < tuple_(c_at, c_id))

    stmt = stmt.limit(limit + 1)
    rows = list(db.execute(stmt).scalars().all())
    next_cur: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cur = _movement_encode_cursor(last.created_at, last.id)

    shop_ids = {r.shop_id for r in rows}
    prod_ids = {r.product_id for r in rows}
    shops = {s.id: s for s in db.execute(select(Shop).where(Shop.id.in_(shop_ids))).scalars().all()} if shop_ids else {}
    prods = {p.id: p for p in db.execute(select(Product).where(Product.id.in_(prod_ids))).scalars().all()} if prod_ids else {}

    items = [
        StockMovementOut(
            id=r.id,
            tenant_id=r.tenant_id,
            shop_id=r.shop_id,
            shop_name=shops[r.shop_id].name if r.shop_id in shops else None,
            product_id=r.product_id,
            product_sku=prods[r.product_id].sku if r.product_id in prods else None,
            product_name=prods[r.product_id].name if r.product_id in prods else None,
            quantity_delta=r.quantity_delta,
            movement_type=r.movement_type,
            transaction_id=r.transaction_id,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return StockMovementListResponse(items=items, next_cursor=next_cur)


class OperatorOut(BaseModel):
    id: UUID
    email: str
    display_name: str | None = None
    role: str | None = None
    role_id: UUID | None = None
    is_active: bool
    created_at: datetime


class CreateOperatorBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str | None = Field(default=None, max_length=255)
    role_id: UUID


class PatchOperatorBody(BaseModel):
    role_id: UUID | None = None
    is_active: bool | None = None


def _operator_out(r: User) -> OperatorOut:
    return OperatorOut(
        id=r.id,
        email=r.email,
        display_name=r.name,
        role=r.role.name if r.role else None,
        role_id=r.role_id,
        is_active=r.is_active,
        created_at=r.created_at,
    )


@router.get("/operators", response_model=list[OperatorOut], dependencies=[require_permission("operators:read")])
def list_operators(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[OperatorOut]:
    """Lists tenant users with admin_web or admin_mobile access (operators)."""
    tenant_id = _require_operator_tenant(ctx)
    # Only show users whose role has admin web/mobile access
    from app.models import Permission, RolePermission
    rows = db.execute(
        select(User)
        .join(Role, User.role_id == Role.id)
        .join(RolePermission, RolePermission.role_id == Role.id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(
            User.tenant_id == tenant_id,
            Permission.codename.in_(["admin_web:access", "admin_mobile:access"]),
        )
        .distinct()
        .order_by(User.created_at.desc())
    ).scalars().all()
    return [_operator_out(r) for r in rows]


@router.post("/operators", response_model=OperatorOut, status_code=201, dependencies=[require_permission("operators:write")])
def create_operator(
    body: CreateOperatorBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> OperatorOut:
    tenant_id = _require_operator_tenant(ctx)
    role = db.execute(
        select(Role).where(Role.id == body.role_id, Role.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found for this tenant")
    pw_hash = bcrypt.hashpw(body.password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
    operator = User(
        email=body.email.strip().lower(),
        password_hash=pw_hash,
        name=body.display_name or body.email.strip().lower(),
        role_id=body.role_id,
        tenant_id=tenant_id,
        is_active=True,
    )
    db.add(operator)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.user_id, action="create_operator", resource_type="user", resource_id=str(operator.id))
    db.commit()
    db.refresh(operator)
    return _operator_out(operator)


@router.patch("/operators/{operator_id}", response_model=OperatorOut, dependencies=[require_permission("operators:write")])
def patch_operator(
    operator_id: UUID,
    body: PatchOperatorBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> OperatorOut:
    tenant_id = _require_operator_tenant(ctx)
    row = db.get(User, operator_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Operator not found")
    if row.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access is forbidden")
    if body.role_id is not None:
        role = db.execute(
            select(Role).where(Role.id == body.role_id, Role.tenant_id == tenant_id)
        ).scalar_one_or_none()
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found for this tenant")
        # Prevent removing the last owner
        if row.role and row.role.name == "owner":
            owner_count = db.execute(
                select(func.count())
                .select_from(User)
                .join(Role, User.role_id == Role.id)
                .where(User.tenant_id == tenant_id, Role.name == "owner", User.is_active.is_(True))
            ).scalar_one()
            if owner_count <= 1 and role.name != "owner":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Cannot remove the last owner from this tenant",
                )
        row.role_id = body.role_id
    if body.is_active is not None:
        row.is_active = body.is_active
    db.commit()
    db.refresh(row)
    return _operator_out(row)


# ---------------------------------------------------------------------------
# Unified Users endpoint — for the new single Team tab
# ---------------------------------------------------------------------------


class TeamUserOut(BaseModel):
    id: UUID
    email: str
    name: str
    phone: str | None
    role_id: UUID | None
    role_name: str | None
    role_display_name: str | None
    shop_id: UUID | None
    device_id: UUID | None
    access: list[str]  # subset of ["cashier_app", "admin_web", "admin_mobile"]
    has_password: bool
    has_pin: bool
    is_active: bool
    created_at: datetime


@router.get("/users", response_model=list[TeamUserOut], dependencies=[require_permission("operators:read", "staff:read")])
def list_users(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    include_inactive: bool = False,
) -> list[TeamUserOut]:
    """Unified list of all users in the tenant (replaces separate employees/operators endpoints for the Team UI)."""
    tenant_id = _require_operator_tenant(ctx)
    from app.models import Permission, RolePermission

    stmt = select(User).where(User.tenant_id == tenant_id).order_by(User.created_at.desc())
    if not include_inactive:
        stmt = stmt.where(User.is_active.is_(True))
    users = db.execute(stmt).scalars().all()

    # Build role → permissions map in one query
    role_ids = {u.role_id for u in users if u.role_id}
    role_perms: dict[UUID, list[str]] = {rid: [] for rid in role_ids}
    if role_ids:
        rows = db.execute(
            select(RolePermission.role_id, Permission.codename)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(RolePermission.role_id.in_(role_ids))
        ).all()
        for rid, codename in rows:
            role_perms[rid].append(codename)

    access_codenames = {
        "cashier_app:access": "cashier_app",
        "admin_web:access": "admin_web",
        "admin_mobile:access": "admin_mobile",
    }

    out: list[TeamUserOut] = []
    for u in users:
        perms = role_perms.get(u.role_id, []) if u.role_id else []
        access = [access_codenames[p] for p in perms if p in access_codenames]
        out.append(
            TeamUserOut(
                id=u.id,
                email=u.email,
                name=u.name,
                phone=u.phone,
                role_id=u.role_id,
                role_name=u.role.name if u.role else None,
                role_display_name=u.role.display_name if u.role else None,
                shop_id=u.shop_id,
                device_id=u.device_id,
                access=access,
                has_password=bool(u.password_hash),
                has_pin=bool(u.pin_hash),
                is_active=u.is_active,
                created_at=u.created_at,
            )
        )
    return out


class CreateUnifiedUserBody(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    role_id: UUID
    shop_id: UUID | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    pin: str | None = Field(default=None, min_length=4, max_length=8)


@router.post("/users", response_model=TeamUserOut, status_code=201, dependencies=[require_permission("operators:write", "staff:write")])
def create_unified_user(
    body: CreateUnifiedUserBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> TeamUserOut:
    """Unified create-user endpoint — handles both admin-style and cashier-style users."""
    tenant_id = _require_operator_tenant(ctx)
    role = db.execute(
        select(Role).where(Role.id == body.role_id, Role.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found for this tenant")

    if body.pin and not body.pin.isdigit():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PIN must be numeric")

    import bcrypt as _bcrypt
    password_hash = _bcrypt.hashpw(body.password.encode(), _bcrypt.gensalt()).decode() if body.password else None
    pin_hash = _bcrypt.hashpw(body.pin.encode(), _bcrypt.gensalt()).decode() if body.pin else None

    user = User(
        tenant_id=tenant_id,
        shop_id=body.shop_id,
        role_id=body.role_id,
        email=body.email.strip().lower(),
        name=body.name.strip(),
        phone=body.phone.strip() if body.phone else None,
        password_hash=password_hash,
        pin_hash=pin_hash,
        is_active=True,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use for this tenant")
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.user_id, action="create_user", resource_type="user", resource_id=str(user.id))
    db.commit()
    db.refresh(user)

    # Build response via the same logic as list_users
    from app.models import Permission, RolePermission
    perms = [p for p, in db.execute(
        select(Permission.codename)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == user.role_id)
    ).all()]
    access_codenames = {"cashier_app:access": "cashier_app", "admin_web:access": "admin_web", "admin_mobile:access": "admin_mobile"}
    access = [access_codenames[p] for p in perms if p in access_codenames]

    return TeamUserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        phone=user.phone,
        role_id=user.role_id,
        role_name=role.name,
        role_display_name=role.display_name,
        shop_id=user.shop_id,
        device_id=user.device_id,
        access=access,
        has_password=bool(user.password_hash),
        has_pin=bool(user.pin_hash),
        is_active=user.is_active,
        created_at=user.created_at,
    )


class PatchUnifiedUserBody(BaseModel):
    name: str | None = None
    phone: str | None = None
    role_id: UUID | None = None
    shop_id: UUID | None = None
    is_active: bool | None = None


@router.patch("/users/{user_id}", response_model=TeamUserOut, dependencies=[require_permission("operators:write", "staff:write")])
def patch_unified_user(
    user_id: UUID,
    body: PatchUnifiedUserBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> TeamUserOut:
    tenant_id = _require_operator_tenant(ctx)
    row = db.get(User, user_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if body.role_id is not None:
        role = db.execute(select(Role).where(Role.id == body.role_id, Role.tenant_id == tenant_id)).scalar_one_or_none()
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
        row.role_id = body.role_id
    if body.name is not None:
        row.name = body.name.strip()
    if body.phone is not None:
        row.phone = body.phone.strip() or None
    if body.shop_id is not None:
        row.shop_id = body.shop_id
    if body.is_active is not None:
        row.is_active = body.is_active

    write_audit(db, tenant_id=tenant_id, operator_id=ctx.user_id, action="update_user", resource_type="user", resource_id=str(user_id))
    db.commit()
    db.refresh(row)

    from app.models import Permission, RolePermission
    perms = [p for p, in db.execute(
        select(Permission.codename)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == row.role_id)
    ).all()] if row.role_id else []
    access_codenames = {"cashier_app:access": "cashier_app", "admin_web:access": "admin_web", "admin_mobile:access": "admin_mobile"}
    access = [access_codenames[p] for p in perms if p in access_codenames]

    return TeamUserOut(
        id=row.id, email=row.email, name=row.name, phone=row.phone,
        role_id=row.role_id, role_name=row.role.name if row.role else None,
        role_display_name=row.role.display_name if row.role else None,
        shop_id=row.shop_id, device_id=row.device_id, access=access,
        has_password=bool(row.password_hash), has_pin=bool(row.pin_hash),
        is_active=row.is_active, created_at=row.created_at,
    )


class CreateShopBody(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class CreateShopResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str


class ShopSummaryOut(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    created_at: datetime


@router.get("/shops", response_model=list[ShopSummaryOut], dependencies=[require_permission("shops:read")])
def admin_list_shops(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    tenant_id: UUID | None = None,
) -> list[ShopSummaryOut]:
    tenant_id = _coerce_tenant_scope(ctx, tenant_id)
    stmt = select(Shop).order_by(Shop.tenant_id, Shop.name)
    stmt = stmt.where(Shop.tenant_id == tenant_id)
    rows = db.execute(stmt).scalars().all()
    return [ShopSummaryOut(id=r.id, tenant_id=r.tenant_id, name=r.name, created_at=r.created_at) for r in rows]


@router.post("/shops", response_model=CreateShopResponse, dependencies=[require_permission("shops:write")])
def admin_create_shop(
    body: CreateShopBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> CreateShopResponse:
    tenant_id = _require_operator_tenant(ctx)
    shop = Shop(tenant_id=tenant_id, name=body.name.strip())
    db.add(shop)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A shop with this name already exists.") from None
    write_audit(
        db,
        tenant_id=tenant_id,
        operator_id=ctx.operator_id,
        action="create_shop",
        resource_type="shop",
        resource_id=str(shop.id),
        after={"name": shop.name},
    )
    db.commit()
    db.refresh(shop)
    return CreateShopResponse(id=shop.id, tenant_id=shop.tenant_id, name=shop.name)


class CreateProductBody(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    unit_price_cents: int = Field(ge=0)
    category: str | None = Field(default=None, max_length=128)
    product_group_id: UUID | None = None
    variant_label: str | None = Field(default=None, max_length=128)
    barcode: str | None = Field(default=None, max_length=128)
    cost_price_cents: int | None = Field(default=None, ge=0)
    mrp_cents: int | None = Field(default=None, ge=0)
    hsn_code: str | None = Field(default=None, max_length=32)
    negative_inventory_allowed: bool = False


class CreateProductResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    sku: str
    name: str
    unit_price_cents: int
    category: str | None
    product_group_id: UUID | None = None
    group_title: str | None = None
    variant_label: str | None = None
    reorder_point: int = 0
    barcode: str | None = None
    cost_price_cents: int | None = None
    mrp_cents: int | None = None
    hsn_code: str | None = None
    negative_inventory_allowed: bool = False


def _resolve_product_group(
    db: Session, tenant_id: UUID, product_group_id: UUID | None
) -> ProductGroup | None:
    if product_group_id is None:
        return None
    g = db.get(ProductGroup, product_group_id)
    if g is None or g.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="product_group_not_found",
        )
    return g


class ProductListItem(BaseModel):
    id: UUID
    sku: str
    name: str
    status: str
    category: str | None
    unit_price_cents: int
    reorder_point: int
    variant_label: str | None = None
    group_title: str | None = None
    barcode: str | None = None
    cost_price_cents: int | None = None
    mrp_cents: int | None = None


@router.get("/products", response_model=list[ProductListItem], dependencies=[require_permission("catalog:read")])
def admin_list_products(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    q: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    category: str | None = None,
) -> list[ProductListItem]:
    tenant_id = _require_operator_tenant(ctx)
    stmt = select(Product).options(selectinload(Product.product_group)).order_by(Product.name.asc())
    stmt = stmt.where(Product.tenant_id == tenant_id)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Product.name.ilike(like), Product.sku.ilike(like)))
    if status_filter:
        stmt = stmt.where(Product.status == status_filter)
    if category and category.strip():
        stmt = stmt.where(Product.category == category.strip())
    rows = db.execute(stmt).scalars().all()
    return [
        ProductListItem(
            id=r.id,
            sku=r.sku,
            name=r.name,
            status=r.status,
            category=r.category,
            unit_price_cents=r.unit_price_cents,
            reorder_point=r.reorder_point,
            variant_label=r.variant_label,
            group_title=r.product_group.title if r.product_group else None,
            barcode=r.barcode,
            cost_price_cents=r.cost_price_cents,
            mrp_cents=r.mrp_cents,
        )
        for r in rows
    ]


@router.post("/products", response_model=CreateProductResponse, dependencies=[require_permission("catalog:write")])
def admin_create_product(
    body: CreateProductBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> CreateProductResponse:
    tenant_id = _require_operator_tenant(ctx)
    group = _resolve_product_group(db, tenant_id, body.product_group_id)
    prod = Product(
        tenant_id=tenant_id,
        product_group_id=group.id if group else None,
        sku=body.sku.strip(),
        name=body.name.strip(),
        unit_price_cents=body.unit_price_cents,
        category=body.category.strip() if body.category else None,
        variant_label=body.variant_label.strip() if body.variant_label else None,
        barcode=body.barcode.strip() if body.barcode else None,
        cost_price_cents=body.cost_price_cents,
        mrp_cents=body.mrp_cents,
        hsn_code=body.hsn_code.strip() if body.hsn_code else None,
        negative_inventory_allowed=body.negative_inventory_allowed,
    )
    db.add(prod)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="sku_conflict") from None
    write_audit(
        db,
        tenant_id=tenant_id,
        operator_id=ctx.operator_id,
        action="create_product",
        resource_type="product",
        resource_id=str(prod.id),
        after={"sku": prod.sku, "name": prod.name, "status": prod.status},
    )
    db.commit()
    db.refresh(prod)
    return CreateProductResponse(
        id=prod.id,
        tenant_id=prod.tenant_id,
        sku=prod.sku,
        name=prod.name,
        unit_price_cents=prod.unit_price_cents,
        category=prod.category,
        product_group_id=prod.product_group_id,
        group_title=group.title if group else None,
        variant_label=prod.variant_label,
        reorder_point=prod.reorder_point,
        barcode=prod.barcode,
        cost_price_cents=prod.cost_price_cents,
        mrp_cents=prod.mrp_cents,
        hsn_code=prod.hsn_code,
        negative_inventory_allowed=prod.negative_inventory_allowed,
    )


class ProductGroupOut(BaseModel):
    id: UUID
    tenant_id: UUID
    title: str
    notes: str | None
    created_at: datetime


class CreateProductGroupBody(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    notes: str | None = None


@router.post("/product-groups", response_model=ProductGroupOut, dependencies=[require_permission("catalog:write")])
def admin_create_product_group(
    body: CreateProductGroupBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ProductGroupOut:
    tenant_id = _require_operator_tenant(ctx)
    row = ProductGroup(
        tenant_id=tenant_id,
        title=body.title.strip(),
        notes=body.notes.strip() if body.notes else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ProductGroupOut(
        id=row.id,
        tenant_id=row.tenant_id,
        title=row.title,
        notes=row.notes,
        created_at=row.created_at,
    )


@router.get("/product-groups", response_model=list[ProductGroupOut], dependencies=[require_permission("catalog:read")])
def admin_list_product_groups(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    tenant_id: UUID | None = None,
) -> list[ProductGroupOut]:
    tenant_id = _coerce_tenant_scope(ctx, tenant_id)
    rows = db.execute(
        select(ProductGroup)
        .where(ProductGroup.tenant_id == tenant_id)
        .order_by(ProductGroup.title.asc())
    ).scalars().all()
    return [
        ProductGroupOut(
            id=r.id,
            tenant_id=r.tenant_id,
            title=r.title,
            notes=r.notes,
            created_at=r.created_at,
        )
        for r in rows
    ]


_VALID_PRODUCT_STATUSES = {"active", "draft", "archived", "discontinued"}


class PatchProductBody(BaseModel):
    product_group_id: UUID | None = None
    variant_label: str | None = Field(default=None, max_length=128)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = None
    category: str | None = Field(default=None, max_length=128)
    unit_price_cents: int | None = Field(default=None, ge=0)
    reorder_point: int | None = Field(default=None, ge=0)
    barcode: str | None = Field(default=None, max_length=128)
    cost_price_cents: int | None = Field(default=None, ge=0)
    mrp_cents: int | None = Field(default=None, ge=0)
    hsn_code: str | None = Field(default=None, max_length=32)
    negative_inventory_allowed: bool | None = None


@router.patch("/products/{product_id}", response_model=CreateProductResponse, dependencies=[require_permission("catalog:write")])
def admin_patch_product(
    product_id: UUID,
    body: PatchProductBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> CreateProductResponse:
    tenant_id = _require_operator_tenant(ctx)
    prod = db.get(Product, product_id)
    if prod is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if prod.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access is forbidden")

    patch = body.model_dump(exclude_unset=True)
    before_snap = {"name": prod.name, "status": prod.status, "unit_price_cents": prod.unit_price_cents}
    if "name" in patch and patch["name"] is not None:
        prod.name = patch["name"].strip()

    if "variant_label" in patch:
        vl = patch["variant_label"]
        prod.variant_label = vl.strip() if isinstance(vl, str) and vl.strip() else None

    if "status" in patch and patch["status"] is not None:
        if patch["status"] not in _VALID_PRODUCT_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status '{patch['status']}'. Must be one of: {', '.join(sorted(_VALID_PRODUCT_STATUSES))}",
            )
        prod.status = patch["status"]

    if "category" in patch:
        cat = patch["category"]
        prod.category = cat.strip() if isinstance(cat, str) and cat.strip() else None

    if "unit_price_cents" in patch and patch["unit_price_cents"] is not None:
        prod.unit_price_cents = patch["unit_price_cents"]

    if "reorder_point" in patch and patch["reorder_point"] is not None:
        prod.reorder_point = patch["reorder_point"]

    if "barcode" in patch:
        bc = patch["barcode"]
        prod.barcode = bc.strip() if isinstance(bc, str) and bc.strip() else None

    if "cost_price_cents" in patch:
        prod.cost_price_cents = patch["cost_price_cents"]

    if "mrp_cents" in patch:
        prod.mrp_cents = patch["mrp_cents"]

    if "hsn_code" in patch:
        hs = patch["hsn_code"]
        prod.hsn_code = hs.strip() if isinstance(hs, str) and hs.strip() else None

    if "negative_inventory_allowed" in patch and patch["negative_inventory_allowed"] is not None:
        prod.negative_inventory_allowed = patch["negative_inventory_allowed"]

    group_title: str | None = None
    if "product_group_id" in patch:
        gid = patch["product_group_id"]
        if gid is None:
            prod.product_group_id = None
        else:
            g = _resolve_product_group(db, prod.tenant_id, gid)
            prod.product_group_id = g.id
            group_title = g.title

    write_audit(
        db,
        tenant_id=tenant_id,
        operator_id=ctx.operator_id,
        action="update_product",
        resource_type="product",
        resource_id=str(product_id),
        before=before_snap,
        after={"name": prod.name, "status": prod.status, "unit_price_cents": prod.unit_price_cents},
    )
    db.commit()
    db.refresh(prod)
    if prod.product_group_id is not None:
        g_out = db.get(ProductGroup, prod.product_group_id)
        group_title = g_out.title if g_out else None

    return CreateProductResponse(
        id=prod.id,
        tenant_id=prod.tenant_id,
        sku=prod.sku,
        name=prod.name,
        unit_price_cents=prod.unit_price_cents,
        category=prod.category,
        product_group_id=prod.product_group_id,
        group_title=group_title,
        variant_label=prod.variant_label,
        reorder_point=prod.reorder_point,
        barcode=prod.barcode,
        cost_price_cents=prod.cost_price_cents,
        mrp_cents=prod.mrp_cents,
        hsn_code=prod.hsn_code,
        negative_inventory_allowed=prod.negative_inventory_allowed,
    )


# ---------------------------------------------------------------------------
# Bulk reorder point
# ---------------------------------------------------------------------------


class BulkReorderPointBody(BaseModel):
    product_ids: list[UUID] = Field(min_length=1, max_length=200)
    reorder_point: int = Field(ge=0)


class BulkReorderPointResponse(BaseModel):
    updated_count: int


@router.post("/products/bulk-reorder-point", response_model=BulkReorderPointResponse, dependencies=[require_permission("inventory:write")])
def bulk_set_reorder_point(
    body: BulkReorderPointBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> BulkReorderPointResponse:
    tenant_id = _require_operator_tenant(ctx)
    result = db.execute(
        Product.__table__.update()
        .where(Product.id.in_(body.product_ids), Product.tenant_id == tenant_id)
        .values(reorder_point=body.reorder_point)
    )
    db.commit()
    return BulkReorderPointResponse(updated_count=result.rowcount)


# ---------------------------------------------------------------------------
# Stock adjustments
# ---------------------------------------------------------------------------

import uuid as _uuid_mod  # noqa: E402 — local import to avoid name conflicts

_VALID_REASONS = {"correction", "damage", "loss", "found", "other"}


class AdjustmentIn(BaseModel):
    shop_id: UUID
    product_id: UUID
    quantity_delta: int = Field(ne=0)
    reason: str
    notes: str | None = None


@router.post("/inventory/adjustments", response_model=StockMovementOut, status_code=status.HTTP_201_CREATED, dependencies=[require_permission("inventory:write")])
def create_stock_adjustment(
    body: AdjustmentIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> StockMovementOut:
    tenant_id = _require_operator_tenant(ctx)

    if body.reason not in _VALID_REASONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid reason '{body.reason}'. Must be one of: {', '.join(sorted(_VALID_REASONS))}",
        )

    shop = db.get(Shop, body.shop_id)
    if shop is None or shop.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")

    prod = db.get(Product, body.product_id)
    if prod is None or prod.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    adj = StockAdjustment(
        id=_uuid_mod.uuid4(),
        tenant_id=tenant_id,
        shop_id=body.shop_id,
        product_id=body.product_id,
        quantity_delta=body.quantity_delta,
        reason_code=body.reason,
        notes=body.notes,
        approved_by_user_id=ctx.user_id,
        created_by_user_id=ctx.user_id,
        status="approved",
    )
    db.add(adj)

    idempotency_key = f"adj-{adj.id}"
    movement = StockMovement(
        id=_uuid_mod.uuid4(),
        tenant_id=tenant_id,
        shop_id=body.shop_id,
        product_id=body.product_id,
        quantity_delta=body.quantity_delta,
        movement_type="adjustment",
        idempotency_key=idempotency_key,
    )
    db.add(movement)
    db.commit()
    db.refresh(movement)

    return StockMovementOut(
        id=movement.id,
        tenant_id=movement.tenant_id,
        shop_id=movement.shop_id,
        shop_name=shop.name,
        product_id=movement.product_id,
        product_sku=prod.sku,
        product_name=prod.name,
        quantity_delta=movement.quantity_delta,
        movement_type=movement.movement_type,
        transaction_id=None,
        created_at=movement.created_at,
    )
