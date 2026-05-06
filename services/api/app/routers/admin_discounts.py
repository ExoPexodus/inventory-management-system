"""Admin endpoints for discounts + the public discount-apply endpoint."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Discount, DiscountUse
from app.services.discount_service import (
    DiscountNotEligibleError, DiscountNotFoundError, apply_discount,
)

router = APIRouter(tags=["Admin Discounts"])

_VALID_TYPES = {"percentage", "fixed_amount", "free_shipping"}
_VALID_STATUSES = {"active", "paused", "scheduled"}


class DiscountIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, min_length=1, max_length=128)
    discount_type: str
    value_bps: int | None = Field(default=None, ge=1, le=10000)
    value_cents: int | None = Field(default=None, ge=1)
    channel_id: UUID | None = None
    status: str = "active"
    stackable: bool = False
    priority: int = 0
    min_subtotal_cents: int | None = Field(default=None, ge=0)
    max_uses_total: int | None = Field(default=None, ge=1)
    max_uses_per_customer: int | None = Field(default=None, ge=1)
    starts_at: datetime | None = None
    expires_at: datetime | None = None


class DiscountPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = None
    stackable: bool | None = None
    priority: int | None = None
    min_subtotal_cents: int | None = None
    max_uses_total: int | None = None
    max_uses_per_customer: int | None = None
    starts_at: datetime | None = None
    expires_at: datetime | None = None


class DiscountOut(BaseModel):
    id: UUID
    tenant_id: UUID
    channel_id: UUID | None
    name: str
    code: str | None
    discount_type: str
    value_bps: int | None
    value_cents: int | None
    status: str
    stackable: bool
    priority: int
    min_subtotal_cents: int | None
    max_uses_total: int | None
    max_uses_per_customer: int | None
    starts_at: datetime | None
    expires_at: datetime | None
    times_used: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DiscountApplyIn(BaseModel):
    channel_id: UUID
    code: str | None = None
    cart_subtotal_cents: int = Field(ge=0)
    customer_id: UUID | None = None


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Operator not assigned to a tenant")
    return ctx.tenant_id


def _get_or_404(db: Session, discount_id: UUID, tenant_id: UUID) -> Discount:
    d = db.get(Discount, discount_id)
    if d is None or d.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Discount not found")
    return d


def _times_used(db: Session, discount_id: UUID) -> int:
    return db.execute(
        select(func.count(DiscountUse.id)).where(DiscountUse.discount_id == discount_id)
    ).scalar_one()


def _to_out(db: Session, d: Discount) -> DiscountOut:
    return DiscountOut(
        id=d.id, tenant_id=d.tenant_id, channel_id=d.channel_id,
        name=d.name, code=d.code, discount_type=d.discount_type,
        value_bps=d.value_bps, value_cents=d.value_cents,
        status=d.status, stackable=d.stackable, priority=d.priority,
        min_subtotal_cents=d.min_subtotal_cents,
        max_uses_total=d.max_uses_total, max_uses_per_customer=d.max_uses_per_customer,
        starts_at=d.starts_at, expires_at=d.expires_at,
        times_used=_times_used(db, d.id),
        created_at=d.created_at, updated_at=d.updated_at,
    )


def _validate_discount_type_and_value(discount_type: str, value_bps: int | None, value_cents: int | None) -> None:
    """Validate cross-field constraints, raising HTTP 400 on failure."""
    if discount_type not in _VALID_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"discount_type must be one of {sorted(_VALID_TYPES)}",
        )
    if discount_type == "percentage" and not value_bps:
        raise HTTPException(
            status_code=400,
            detail="value_bps is required for percentage discounts",
        )
    if discount_type == "fixed_amount" and not value_cents:
        raise HTTPException(
            status_code=400,
            detail="value_cents is required for fixed_amount discounts",
        )


@router.get("/v1/admin/discounts", response_model=list[DiscountOut],
            dependencies=[require_permission("discounts:manage")])
def list_discounts(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[DiscountOut]:
    tenant_id = _require_tenant(ctx)
    rows = db.execute(
        select(Discount).where(Discount.tenant_id == tenant_id)
        .order_by(Discount.priority.desc(), Discount.name)
    ).scalars().all()
    return [_to_out(db, r) for r in rows]


@router.post("/v1/admin/discounts", response_model=DiscountOut,
             status_code=status.HTTP_201_CREATED,
             dependencies=[require_permission("discounts:manage")])
def create_discount(
    body: DiscountIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> DiscountOut:
    tenant_id = _require_tenant(ctx)
    if body.status not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(_VALID_STATUSES)}")
    _validate_discount_type_and_value(body.discount_type, body.value_bps, body.value_cents)

    disc = Discount(
        tenant_id=tenant_id,
        channel_id=body.channel_id,
        name=body.name,
        code=body.code.upper() if body.code else None,
        discount_type=body.discount_type,
        value_bps=body.value_bps,
        value_cents=body.value_cents,
        status=body.status,
        stackable=body.stackable,
        priority=body.priority,
        min_subtotal_cents=body.min_subtotal_cents,
        max_uses_total=body.max_uses_total,
        max_uses_per_customer=body.max_uses_per_customer,
        starts_at=body.starts_at,
        expires_at=body.expires_at,
    )
    db.add(disc)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=409,
                            detail=f"A discount with code {body.code!r} already exists for this tenant")
    db.refresh(disc)
    return _to_out(db, disc)


@router.patch("/v1/admin/discounts/{discount_id}", response_model=DiscountOut,
              dependencies=[require_permission("discounts:manage")])
def update_discount(
    discount_id: UUID,
    body: DiscountPatch,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> DiscountOut:
    tenant_id = _require_tenant(ctx)
    disc = _get_or_404(db, discount_id, tenant_id)
    updates = body.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(_VALID_STATUSES)}")
    for field, value in updates.items():
        setattr(disc, field, value)
    db.commit()
    db.refresh(disc)
    return _to_out(db, disc)


@router.delete("/v1/admin/discounts/{discount_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[require_permission("discounts:manage")])
def delete_discount(
    discount_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    disc = _get_or_404(db, discount_id, tenant_id)
    db.delete(disc)
    db.commit()


@router.post("/v1/discounts/apply")
def apply(
    body: DiscountApplyIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> dict[str, Any]:
    """Public discount calculator. Returns 404 if code not found, 422 if ineligible."""
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Operator not assigned to a tenant")
    try:
        return apply_discount(
            db, tenant_id=ctx.tenant_id, channel_id=body.channel_id,
            code=body.code, cart_subtotal_cents=body.cart_subtotal_cents,
            customer_id=body.customer_id,
        )
    except DiscountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except DiscountNotEligibleError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
