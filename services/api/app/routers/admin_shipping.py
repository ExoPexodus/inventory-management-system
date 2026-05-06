"""Admin endpoints for shipping zones + rates, plus the public shipping calculator.

Admin endpoints (zones/rates CRUD) require `shipping:manage` permission.
The calculate endpoint uses admin auth context but has no permission gate —
it's consumed by headless frontends and hosted checkout.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Channel, ShippingRate, ShippingZone
from app.services.shipping_service import calculate_shipping_options

router = APIRouter(tags=["Admin Shipping"])

_VALID_CONDITION_TYPES = {"none", "by_total", "by_weight", "by_items"}


# ── Schemas ──

class ShippingZoneIn(BaseModel):
    channel_id: UUID
    name: str = Field(min_length=1, max_length=255)
    countries: list[str] = Field(default_factory=list)
    is_catch_all: bool = False


class ShippingZoneOut(BaseModel):
    id: UUID
    tenant_id: UUID
    channel_id: UUID
    name: str
    countries: list[str] | None
    is_catch_all: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ShippingRateIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    base_price_cents: int = Field(ge=0)
    currency_code: str = Field(min_length=3, max_length=3)
    free_above_cents: int | None = Field(default=None, ge=0)
    condition_type: str = "none"
    condition_min: int | None = Field(default=None, ge=0)
    condition_max: int | None = Field(default=None, ge=0)
    applies_to_classes: list[str] | None = None


class ShippingRateOut(BaseModel):
    id: UUID
    tenant_id: UUID
    zone_id: UUID
    name: str
    base_price_cents: int
    currency_code: str
    free_above_cents: int | None
    condition_type: str
    condition_min: int | None
    condition_max: int | None
    applies_to_classes: list[str] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ShippingCalculateDestination(BaseModel):
    country: str = Field(min_length=2, max_length=2)


class ShippingCalculateLineIn(BaseModel):
    product_id: UUID
    quantity: int = Field(ge=1)
    unit_price_cents: int = Field(ge=0)


class ShippingCalculateIn(BaseModel):
    channel_id: UUID
    destination: ShippingCalculateDestination
    cart_lines: list[ShippingCalculateLineIn]
    cart_subtotal_cents: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)


class ShippingOptionOut(BaseModel):
    rate_id: UUID
    zone_id: UUID
    name: str
    price_cents: int
    currency_code: str
    is_free: bool


# ── Helpers ──

def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator not assigned to a tenant",
        )
    return ctx.tenant_id


def _get_zone_or_404(db: Session, zone_id: UUID, tenant_id: UUID) -> ShippingZone:
    zone = db.get(ShippingZone, zone_id)
    if zone is None or zone.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
    return zone


# ── Zone routes ──

@router.get(
    "/v1/admin/shipping/zones",
    response_model=list[ShippingZoneOut],
    dependencies=[require_permission("shipping:manage")],
)
def list_zones(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    channel_id: UUID | None = Query(default=None),
) -> list[ShippingZone]:
    tenant_id = _require_tenant(ctx)
    q = select(ShippingZone).where(ShippingZone.tenant_id == tenant_id)
    if channel_id:
        q = q.where(ShippingZone.channel_id == channel_id)
    return list(db.execute(q.order_by(ShippingZone.name)).scalars().all())


@router.post(
    "/v1/admin/shipping/zones",
    response_model=ShippingZoneOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("shipping:manage")],
)
def create_zone(
    body: ShippingZoneIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ShippingZone:
    tenant_id = _require_tenant(ctx)

    ch = db.get(Channel, body.channel_id)
    if ch is None or ch.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="channel_id does not belong to this tenant",
        )

    zone = ShippingZone(
        tenant_id=tenant_id,
        channel_id=body.channel_id,
        name=body.name,
        countries=[c.upper() for c in body.countries],
        is_catch_all=body.is_catch_all,
    )
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return zone


@router.delete(
    "/v1/admin/shipping/zones/{zone_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("shipping:manage")],
)
def delete_zone(
    zone_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    zone = _get_zone_or_404(db, zone_id, tenant_id)
    db.delete(zone)
    db.commit()


# ── Rate routes ──

@router.get(
    "/v1/admin/shipping/zones/{zone_id}/rates",
    response_model=list[ShippingRateOut],
    dependencies=[require_permission("shipping:manage")],
)
def list_rates(
    zone_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[ShippingRate]:
    tenant_id = _require_tenant(ctx)
    _get_zone_or_404(db, zone_id, tenant_id)
    return list(db.execute(
        select(ShippingRate).where(ShippingRate.zone_id == zone_id).order_by(ShippingRate.name)
    ).scalars().all())


@router.post(
    "/v1/admin/shipping/zones/{zone_id}/rates",
    response_model=ShippingRateOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("shipping:manage")],
)
def create_rate(
    zone_id: UUID,
    body: ShippingRateIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ShippingRate:
    tenant_id = _require_tenant(ctx)
    zone = _get_zone_or_404(db, zone_id, tenant_id)

    if body.condition_type not in _VALID_CONDITION_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid condition_type. Allowed: {sorted(_VALID_CONDITION_TYPES)}",
        )

    rate = ShippingRate(
        tenant_id=tenant_id,
        zone_id=zone.id,
        name=body.name,
        base_price_cents=body.base_price_cents,
        currency_code=body.currency_code.upper(),
        free_above_cents=body.free_above_cents,
        condition_type=body.condition_type,
        condition_min=body.condition_min,
        condition_max=body.condition_max,
        applies_to_classes=body.applies_to_classes,
    )
    db.add(rate)
    db.commit()
    db.refresh(rate)
    return rate


@router.delete(
    "/v1/admin/shipping/zones/{zone_id}/rates/{rate_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("shipping:manage")],
)
def delete_rate(
    zone_id: UUID,
    rate_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    _get_zone_or_404(db, zone_id, tenant_id)
    rate = db.get(ShippingRate, rate_id)
    if rate is None or rate.zone_id != zone_id or rate.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rate not found")
    db.delete(rate)
    db.commit()


# ── Public calculate ──

@router.post("/v1/shipping/calculate", response_model=list[ShippingOptionOut])
def calculate(
    body: ShippingCalculateIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[dict[str, Any]]:
    """Public shipping calculator consumed by headless frontends and hosted checkout."""
    return calculate_shipping_options(
        db,
        channel_id=body.channel_id,
        destination_country=body.destination.country,
        cart_lines=[line.model_dump() for line in body.cart_lines],
        cart_subtotal_cents=body.cart_subtotal_cents,
        currency=body.currency,
    )
