"""Admin purchase order endpoints."""

from __future__ import annotations

import uuid as _uuid
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.services.audit_service import write_audit
from app.models import (
    Product,
    PurchaseOrder,
    PurchaseOrderLine,
    Shop,
    StockMovement,
    Supplier,
)

router = APIRouter(prefix="/v1/admin/purchase-orders", tags=["Admin Purchase Orders"])

VALID_STATUSES = {"draft", "ordered", "received", "cancelled"}
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"ordered", "cancelled"},
    "ordered": {"received", "cancelled"},
    "received": set(),
    "cancelled": set(),
}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class POLineIn(BaseModel):
    product_id: UUID
    quantity_ordered: int = Field(gt=0)
    unit_cost_cents: int = Field(ge=0)


class POLineOut(BaseModel):
    id: UUID
    product_id: UUID
    product_name: str
    product_sku: str
    quantity_ordered: int
    quantity_received: int
    unit_cost_cents: int


class POIn(BaseModel):
    supplier_id: UUID
    notes: str | None = None
    expected_delivery_date: datetime | None = None


class POPatchIn(BaseModel):
    notes: str | None = None
    expected_delivery_date: datetime | None = None
    status: str | None = None


class POOut(BaseModel):
    id: UUID
    supplier_id: UUID
    supplier_name: str
    status: str
    notes: str | None
    expected_delivery_date: datetime | None
    created_at: datetime
    updated_at: datetime
    lines: list[POLineOut]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_line_out(line: PurchaseOrderLine, db: Session) -> POLineOut:
    prod = db.get(Product, line.product_id)
    return POLineOut(
        id=line.id,
        product_id=line.product_id,
        product_name=prod.name if prod else "Unknown",
        product_sku=prod.sku if prod else "",
        quantity_ordered=line.quantity_ordered,
        quantity_received=line.quantity_received,
        unit_cost_cents=line.unit_cost_cents,
    )


def _build_po_out(po: PurchaseOrder, db: Session) -> POOut:
    supplier = db.get(Supplier, po.supplier_id)
    lines_q = db.execute(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == po.id)
    ).scalars().all()
    return POOut(
        id=po.id,
        supplier_id=po.supplier_id,
        supplier_name=supplier.name if supplier else "Unknown",
        status=po.status,
        notes=po.notes,
        expected_delivery_date=po.expected_delivery_date,
        created_at=po.created_at,
        updated_at=po.updated_at,
        lines=[_build_line_out(l, db) for l in lines_q],
    )


def _get_po(db: Session, po_id: UUID, tenant_id: UUID) -> PurchaseOrder:
    po = db.get(PurchaseOrder, po_id)
    if po is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    if po.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access is forbidden")
    return po


def _require_operator_tenant(ctx) -> UUID:  # type: ignore[type-arg]
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


# ---------------------------------------------------------------------------
# List & create
# ---------------------------------------------------------------------------


@router.get("", response_model=list[POOut], dependencies=[require_permission("procurement:read")])
def list_purchase_orders(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    po_status: str | None = Query(default=None, alias="status"),
    supplier_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
) -> list[POOut]:
    tenant_id = _require_operator_tenant(ctx)
    stmt = select(PurchaseOrder).where(PurchaseOrder.tenant_id == tenant_id)
    if po_status:
        stmt = stmt.where(PurchaseOrder.status == po_status)
    if supplier_id:
        stmt = stmt.where(PurchaseOrder.supplier_id == supplier_id)
    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor)
            stmt = stmt.where(PurchaseOrder.created_at < cursor_dt)
        except ValueError:
            pass
    stmt = stmt.order_by(PurchaseOrder.created_at.desc()).limit(limit)
    rows = db.execute(stmt).scalars().all()
    return [_build_po_out(po, db) for po in rows]


@router.post("", response_model=POOut, status_code=status.HTTP_201_CREATED, dependencies=[require_permission("procurement:write")])
def create_purchase_order(
    body: POIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> POOut:
    tenant_id = _require_operator_tenant(ctx)
    supplier = db.get(Supplier, body.supplier_id)
    if supplier is None or supplier.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    po = PurchaseOrder(
        id=_uuid.uuid4(),
        tenant_id=tenant_id,
        supplier_id=body.supplier_id,
        notes=body.notes,
        expected_delivery_date=body.expected_delivery_date,
        created_by_user_id=ctx.user_id,
    )
    db.add(po)
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.operator_id, action="create_purchase_order", resource_type="purchase_order", resource_id=str(po.id))
    db.commit()
    db.refresh(po)
    return _build_po_out(po, db)


# ---------------------------------------------------------------------------
# Get single
# ---------------------------------------------------------------------------


@router.get("/{po_id}", response_model=POOut, dependencies=[require_permission("procurement:read")])
def get_purchase_order(
    po_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> POOut:
    tenant_id = _require_operator_tenant(ctx)
    po = _get_po(db, po_id, tenant_id)
    return _build_po_out(po, db)


# ---------------------------------------------------------------------------
# Patch (status transitions + metadata)
# ---------------------------------------------------------------------------


@router.patch("/{po_id}", response_model=POOut, dependencies=[require_permission("procurement:write")])
def patch_purchase_order(
    po_id: UUID,
    body: POPatchIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> POOut:
    tenant_id = _require_operator_tenant(ctx)
    po = _get_po(db, po_id, tenant_id)

    patch = body.model_dump(exclude_unset=True)

    if "notes" in patch:
        po.notes = patch["notes"]
    if "expected_delivery_date" in patch:
        po.expected_delivery_date = patch["expected_delivery_date"]

    if "status" in patch and patch["status"] is not None:
        new_status = patch["status"]
        if new_status not in VALID_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status '{new_status}'",
            )
        if new_status not in ALLOWED_TRANSITIONS.get(po.status, set()):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Cannot transition from '{po.status}' to '{new_status}'",
            )

        if new_status == "received":
            _receive_purchase_order(po, tenant_id, ctx.operator_id, db)

        po.status = new_status

    po.updated_at = datetime.now(UTC)
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.operator_id, action="update_purchase_order", resource_type="purchase_order", resource_id=str(po_id))
    db.commit()
    db.refresh(po)
    return _build_po_out(po, db)


def _receive_purchase_order(po: PurchaseOrder, tenant_id: UUID, operator_id: UUID | None, db: Session) -> None:
    """Create StockMovements for all lines and mark quantity_received."""
    lines = db.execute(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == po.id)
    ).scalars().all()

    # We need the shop_id — purchase orders don't store it directly; use first shop of tenant
    # Prefer supplier-linked shop if available; fall back to first tenant shop.
    first_shop = db.execute(
        select(Shop).where(Shop.tenant_id == tenant_id).limit(1)
    ).scalar_one_or_none()
    if first_shop is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No shops found for tenant; cannot record stock receipt",
        )

    for line in lines:
        if line.quantity_ordered <= 0:
            continue
        idempotency_key = f"po-receipt-{po.id}-{line.id}"
        existing = db.execute(
            select(StockMovement).where(
                StockMovement.tenant_id == tenant_id,
                StockMovement.shop_id == first_shop.id,
                StockMovement.product_id == line.product_id,
                StockMovement.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
        if existing is None:
            movement = StockMovement(
                id=_uuid.uuid4(),
                tenant_id=tenant_id,
                shop_id=first_shop.id,
                product_id=line.product_id,
                quantity_delta=line.quantity_ordered,
                movement_type="purchase_receipt",
                idempotency_key=idempotency_key,
            )
            db.add(movement)
        line.quantity_received = line.quantity_ordered


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.delete("/{po_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[require_permission("procurement:write")])
def delete_purchase_order(
    po_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_operator_tenant(ctx)
    po = _get_po(db, po_id, tenant_id)
    if po.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only draft purchase orders can be deleted",
        )
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.operator_id, action="delete_purchase_order", resource_type="purchase_order", resource_id=str(po_id))
    db.delete(po)
    db.commit()


# ---------------------------------------------------------------------------
# Lines
# ---------------------------------------------------------------------------


@router.post("/{po_id}/lines", response_model=POOut, status_code=status.HTTP_201_CREATED, dependencies=[require_permission("procurement:write")])
def add_po_line(
    po_id: UUID,
    body: POLineIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> POOut:
    tenant_id = _require_operator_tenant(ctx)
    po = _get_po(db, po_id, tenant_id)
    if po.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Lines can only be added to draft purchase orders",
        )
    prod = db.get(Product, body.product_id)
    if prod is None or prod.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    line = PurchaseOrderLine(
        id=_uuid.uuid4(),
        purchase_order_id=po.id,
        product_id=body.product_id,
        quantity_ordered=body.quantity_ordered,
        unit_cost_cents=body.unit_cost_cents,
    )
    db.add(line)
    po.updated_at = datetime.now(UTC)
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.operator_id, action="add_po_line", resource_type="purchase_order", resource_id=str(po_id))
    db.commit()
    db.refresh(po)
    return _build_po_out(po, db)


class POLinePatchIn(BaseModel):
    quantity_ordered: int | None = Field(default=None, gt=0)
    unit_cost_cents: int | None = Field(default=None, ge=0)


@router.patch("/{po_id}/lines/{line_id}", response_model=POOut, dependencies=[require_permission("procurement:write")])
def patch_po_line(
    po_id: UUID,
    line_id: UUID,
    body: POLinePatchIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> POOut:
    tenant_id = _require_operator_tenant(ctx)
    po = _get_po(db, po_id, tenant_id)
    if po.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Lines can only be modified on draft purchase orders",
        )
    line = db.get(PurchaseOrderLine, line_id)
    if line is None or line.purchase_order_id != po.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line not found")
    patch = body.model_dump(exclude_unset=True)
    if "quantity_ordered" in patch:
        line.quantity_ordered = patch["quantity_ordered"]
    if "unit_cost_cents" in patch:
        line.unit_cost_cents = patch["unit_cost_cents"]
    po.updated_at = datetime.now(UTC)
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.operator_id, action="update_po_line", resource_type="purchase_order", resource_id=str(po_id))
    db.commit()
    db.refresh(po)
    return _build_po_out(po, db)


@router.delete("/{po_id}/lines/{line_id}", response_model=POOut, dependencies=[require_permission("procurement:write")])
def delete_po_line(
    po_id: UUID,
    line_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> POOut:
    tenant_id = _require_operator_tenant(ctx)
    po = _get_po(db, po_id, tenant_id)
    if po.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Lines can only be removed from draft purchase orders",
        )
    line = db.get(PurchaseOrderLine, line_id)
    if line is None or line.purchase_order_id != po.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line not found")
    db.delete(line)
    po.updated_at = datetime.now(UTC)
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.operator_id, action="delete_po_line", resource_type="purchase_order", resource_id=str(po_id))
    db.commit()
    db.refresh(po)
    return _build_po_out(po, db)
