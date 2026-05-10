"""Admin endpoints for inter-shop transfer orders."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Product, Shop, Tenant, TransferOrder, TransferOrderLine
from app.services import transfer_orders as svc

router = APIRouter(prefix="/v1/admin/transfer-orders", tags=["Admin Transfer Orders"])

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class LineInput(BaseModel):
    product_id: UUID
    quantity_requested: int = Field(ge=1)
    line_notes: str | None = None


class TransferCreate(BaseModel):
    from_shop_id: UUID
    to_shop_id: UUID
    lines: list[LineInput] = Field(min_length=1)
    notes: str | None = None


class TransferUpdate(BaseModel):
    lines: list[LineInput] = Field(min_length=1)
    notes: str | None = None


class LineQuantityInput(BaseModel):
    line_id: UUID
    quantity: int = Field(ge=0)


class ShipInput(BaseModel):
    lines: list[LineQuantityInput]


class ReceiveInput(BaseModel):
    lines: list[LineQuantityInput]


class RejectInput(BaseModel):
    reason: str = Field(min_length=1)


class LineOut(BaseModel):
    id: UUID
    product_id: UUID
    product_sku: str | None
    product_name: str | None
    quantity_requested: int
    quantity_shipped: int
    quantity_received: int
    unit_cost_at_transfer_cents: int | None
    line_notes: str | None

    model_config = {"from_attributes": True}


class TransferOut(BaseModel):
    id: UUID
    tenant_id: UUID
    from_shop_id: UUID
    from_shop_name: str | None
    to_shop_id: UUID
    to_shop_name: str | None
    status: str
    created_by_user_id: UUID | None
    approved_by_user_id: UUID | None
    approved_at: datetime | None
    rejected_at: datetime | None
    rejection_reason: str | None
    shipped_at: datetime | None
    received_at: datetime | None
    cancelled_at: datetime | None
    notes: str | None
    lines: list[LineOut]
    created_at: datetime

    model_config = {"from_attributes": True}


class TransferListResponse(BaseModel):
    items: list[TransferOut]
    total: int
    page: int
    per_page: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Operator not assigned to a tenant")
    return ctx.tenant_id


def _get_transfer_or_404(db: Session, transfer_id: UUID, tenant_id: UUID) -> TransferOrder:
    transfer = db.get(TransferOrder, transfer_id)
    if transfer is None or transfer.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transfer order not found")
    return transfer


def _serialize_line(db: Session, line: TransferOrderLine) -> LineOut:
    prod = db.get(Product, line.product_id)
    return LineOut(
        id=line.id,
        product_id=line.product_id,
        product_sku=prod.sku if prod else None,
        product_name=prod.name if prod else None,
        quantity_requested=line.quantity_requested,
        quantity_shipped=line.quantity_shipped,
        quantity_received=line.quantity_received,
        unit_cost_at_transfer_cents=line.unit_cost_at_transfer_cents,
        line_notes=line.line_notes,
    )


def _serialize_transfer(db: Session, transfer: TransferOrder) -> TransferOut:
    from_shop = db.get(Shop, transfer.from_shop_id)
    to_shop = db.get(Shop, transfer.to_shop_id)
    lines = [_serialize_line(db, line) for line in transfer.lines]
    return TransferOut(
        id=transfer.id,
        tenant_id=transfer.tenant_id,
        from_shop_id=transfer.from_shop_id,
        from_shop_name=from_shop.name if from_shop else None,
        to_shop_id=transfer.to_shop_id,
        to_shop_name=to_shop.name if to_shop else None,
        status=transfer.status,
        created_by_user_id=transfer.created_by_user_id,
        approved_by_user_id=transfer.approved_by_user_id,
        approved_at=transfer.approved_at,
        rejected_at=transfer.rejected_at,
        rejection_reason=transfer.rejection_reason,
        shipped_at=transfer.shipped_at,
        received_at=transfer.received_at,
        cancelled_at=transfer.cancelled_at,
        notes=transfer.notes,
        lines=lines,
        created_at=transfer.created_at,
    )


def _lines_input_to_dicts(lines: list[LineInput]) -> list[dict]:
    return [
        {
            "product_id": line.product_id,
            "quantity_requested": line.quantity_requested,
            "line_notes": line.line_notes,
        }
        for line in lines
    ]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=TransferListResponse, dependencies=[require_permission("operations:read")])
def list_transfers(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    status_filter: Annotated[list[str] | None, Query(alias="status")] = None,
    from_shop_id: UUID | None = None,
    to_shop_id: UUID | None = None,
    q: str | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=200),
) -> TransferListResponse:
    tenant_id = _require_tenant(ctx)

    query = select(TransferOrder).where(TransferOrder.tenant_id == tenant_id)

    if status_filter:
        query = query.where(TransferOrder.status.in_(status_filter))
    if from_shop_id:
        query = query.where(TransferOrder.from_shop_id == from_shop_id)
    if to_shop_id:
        query = query.where(TransferOrder.to_shop_id == to_shop_id)
    if q:
        ilike = f"%{q}%"
        query = query.where(
            or_(
                TransferOrder.id.cast(str).ilike(ilike),
                TransferOrder.notes.ilike(ilike),
            )
        )
    if created_after:
        query = query.where(TransferOrder.created_at >= created_after)
    if created_before:
        query = query.where(TransferOrder.created_at <= created_before)

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    items = db.execute(
        query.order_by(TransferOrder.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    ).scalars().all()

    return TransferListResponse(
        items=[_serialize_transfer(db, t) for t in items],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post(
    "",
    response_model=TransferOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("operations:write")],
)
def create_transfer(
    body: TransferCreate,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> TransferOut:
    tenant_id = _require_tenant(ctx)
    transfer = svc.create_transfer(
        db,
        tenant_id=tenant_id,
        from_shop_id=body.from_shop_id,
        to_shop_id=body.to_shop_id,
        created_by_user_id=ctx.user_id,
        lines=_lines_input_to_dicts(body.lines),
        notes=body.notes,
    )
    db.commit()
    db.refresh(transfer)
    return _serialize_transfer(db, transfer)


@router.get("/{transfer_id}", response_model=TransferOut, dependencies=[require_permission("operations:read")])
def get_transfer(
    transfer_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> TransferOut:
    tenant_id = _require_tenant(ctx)
    transfer = _get_transfer_or_404(db, transfer_id, tenant_id)
    return _serialize_transfer(db, transfer)


@router.patch("/{transfer_id}", response_model=TransferOut, dependencies=[require_permission("operations:write")])
def update_transfer(
    transfer_id: UUID,
    body: TransferUpdate,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> TransferOut:
    tenant_id = _require_tenant(ctx)
    transfer = _get_transfer_or_404(db, transfer_id, tenant_id)
    transfer = svc.update_draft(
        db,
        transfer=transfer,
        lines=_lines_input_to_dicts(body.lines),
        notes=body.notes,
    )
    db.commit()
    db.refresh(transfer)
    return _serialize_transfer(db, transfer)


@router.post("/{transfer_id}/submit", response_model=TransferOut, dependencies=[require_permission("operations:write")])
def submit_transfer(
    transfer_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> TransferOut:
    tenant_id = _require_tenant(ctx)
    transfer = _get_transfer_or_404(db, transfer_id, tenant_id)
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    transfer = svc.submit_transfer(db, transfer=transfer, tenant=tenant)
    db.commit()
    db.refresh(transfer)
    return _serialize_transfer(db, transfer)


@router.post(
    "/{transfer_id}/approve",
    response_model=TransferOut,
    dependencies=[require_permission("transfers:approve")],
)
def approve_transfer(
    transfer_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> TransferOut:
    tenant_id = _require_tenant(ctx)
    if ctx.user_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User context required")
    transfer = _get_transfer_or_404(db, transfer_id, tenant_id)
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    transfer = svc.approve_transfer(db, transfer=transfer, tenant=tenant, approving_user_id=ctx.user_id)
    db.commit()
    db.refresh(transfer)
    return _serialize_transfer(db, transfer)


@router.post(
    "/{transfer_id}/reject",
    response_model=TransferOut,
    dependencies=[require_permission("transfers:approve")],
)
def reject_transfer(
    transfer_id: UUID,
    body: RejectInput,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> TransferOut:
    tenant_id = _require_tenant(ctx)
    if ctx.user_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User context required")
    transfer = _get_transfer_or_404(db, transfer_id, tenant_id)
    transfer = svc.reject_transfer(db, transfer=transfer, rejecting_user_id=ctx.user_id, reason=body.reason)
    db.commit()
    db.refresh(transfer)
    return _serialize_transfer(db, transfer)


@router.post("/{transfer_id}/ship", response_model=TransferOut, dependencies=[require_permission("operations:write")])
def ship_transfer(
    transfer_id: UUID,
    body: ShipInput,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> TransferOut:
    tenant_id = _require_tenant(ctx)
    transfer = _get_transfer_or_404(db, transfer_id, tenant_id)
    ship_quantities = {item.line_id: item.quantity for item in body.lines}
    transfer = svc.ship_transfer(db, transfer=transfer, ship_quantities=ship_quantities)
    db.commit()
    db.refresh(transfer)
    return _serialize_transfer(db, transfer)


@router.post(
    "/{transfer_id}/receive",
    response_model=TransferOut,
    dependencies=[require_permission("operations:write")],
)
def receive_transfer(
    transfer_id: UUID,
    body: ReceiveInput,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> TransferOut:
    tenant_id = _require_tenant(ctx)
    transfer = _get_transfer_or_404(db, transfer_id, tenant_id)
    receive_quantities = {item.line_id: item.quantity for item in body.lines}
    transfer = svc.receive_transfer(db, transfer=transfer, receive_quantities=receive_quantities)
    db.commit()
    db.refresh(transfer)
    return _serialize_transfer(db, transfer)


@router.post(
    "/{transfer_id}/cancel",
    response_model=TransferOut,
    dependencies=[require_permission("operations:write")],
)
def cancel_transfer(
    transfer_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> TransferOut:
    tenant_id = _require_tenant(ctx)
    transfer = _get_transfer_or_404(db, transfer_id, tenant_id)
    transfer = svc.cancel_transfer(db, transfer=transfer)
    db.commit()
    db.refresh(transfer)
    return _serialize_transfer(db, transfer)


# committed_to_transfers surfacing is handled via the /v1/inventory/shop/{id}/products endpoint
# (which now includes committed_to_transfers per row). No separate endpoint needed.
