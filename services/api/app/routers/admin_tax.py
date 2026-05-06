"""Admin endpoints for tax regions + rules, plus the public tax calculator.

Admin CRUD requires `tax:manage` permission.
The calculate endpoint is public (no permission gate).
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import TaxRegion, TaxRule
from app.services.tax_service import calculate_tax_for_cart

router = APIRouter(tags=["Admin Tax"])


class TaxComponentIn(BaseModel):
    label: str = Field(min_length=1, max_length=64)
    rate_bps: int = Field(ge=0, le=100_000)


class TaxRegionIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    country_code: str = Field(min_length=2, max_length=2)
    state_code: str | None = None


class TaxRegionOut(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    country_code: str
    state_code: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaxRuleIn(BaseModel):
    tax_class: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=255)
    components: list[TaxComponentIn]


class TaxRuleOut(BaseModel):
    id: UUID
    tenant_id: UUID
    region_id: UUID
    tax_class: str
    label: str
    components: list[dict]
    condition_type: str = "none"
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaxCalculateDestination(BaseModel):
    country: str = Field(min_length=2, max_length=2)
    state: str | None = None


class TaxCalculateLineIn(BaseModel):
    product_id: UUID
    quantity: int = Field(ge=1)
    unit_price_cents: int = Field(ge=0)


class TaxCalculateIn(BaseModel):
    channel_id: UUID
    destination: TaxCalculateDestination
    cart_lines: list[TaxCalculateLineIn]
    currency: str = Field(min_length=3, max_length=3)


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator not assigned to a tenant",
        )
    return ctx.tenant_id


def _get_region_or_404(db: Session, region_id: UUID, tenant_id: UUID) -> TaxRegion:
    region = db.get(TaxRegion, region_id)
    if region is None or region.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Region not found")
    return region


@router.get(
    "/v1/admin/tax/regions",
    response_model=list[TaxRegionOut],
    dependencies=[require_permission("tax:manage")],
)
def list_regions(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[TaxRegion]:
    tenant_id = _require_tenant(ctx)
    return list(db.execute(
        select(TaxRegion).where(TaxRegion.tenant_id == tenant_id)
        .order_by(TaxRegion.country_code, TaxRegion.name)
    ).scalars().all())


@router.post(
    "/v1/admin/tax/regions",
    response_model=TaxRegionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("tax:manage")],
)
def create_region(
    body: TaxRegionIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> TaxRegion:
    tenant_id = _require_tenant(ctx)
    region = TaxRegion(
        tenant_id=tenant_id,
        name=body.name,
        country_code=body.country_code.upper(),
        state_code=body.state_code.upper() if body.state_code else None,
    )
    db.add(region)
    db.commit()
    db.refresh(region)
    return region


@router.delete(
    "/v1/admin/tax/regions/{region_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("tax:manage")],
)
def delete_region(
    region_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    region = _get_region_or_404(db, region_id, tenant_id)
    db.delete(region)
    db.commit()


@router.get(
    "/v1/admin/tax/regions/{region_id}/rules",
    response_model=list[TaxRuleOut],
    dependencies=[require_permission("tax:manage")],
)
def list_rules(
    region_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[TaxRule]:
    tenant_id = _require_tenant(ctx)
    _get_region_or_404(db, region_id, tenant_id)
    return list(db.execute(
        select(TaxRule).where(TaxRule.region_id == region_id).order_by(TaxRule.tax_class)
    ).scalars().all())


@router.post(
    "/v1/admin/tax/regions/{region_id}/rules",
    response_model=TaxRuleOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("tax:manage")],
)
def create_rule(
    region_id: UUID,
    body: TaxRuleIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> TaxRule:
    tenant_id = _require_tenant(ctx)
    region = _get_region_or_404(db, region_id, tenant_id)

    rule = TaxRule(
        tenant_id=tenant_id,
        region_id=region.id,
        tax_class=body.tax_class,
        label=body.label,
        components=[c.model_dump() for c in body.components],
    )
    db.add(rule)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A rule for tax_class '{body.tax_class}' already exists in this region",
        )
    db.refresh(rule)
    return rule


@router.delete(
    "/v1/admin/tax/regions/{region_id}/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("tax:manage")],
)
def delete_rule(
    region_id: UUID,
    rule_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    _get_region_or_404(db, region_id, tenant_id)
    rule = db.get(TaxRule, rule_id)
    if rule is None or rule.region_id != region_id or rule.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    db.delete(rule)
    db.commit()


@router.post("/v1/tax/calculate")
def calculate(
    body: TaxCalculateIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> dict[str, Any]:
    """Public tax calculator consumed by headless frontends and hosted checkout."""
    return calculate_tax_for_cart(
        db,
        channel_id=body.channel_id,
        destination_country=body.destination.country,
        destination_state=body.destination.state,
        cart_lines=[line.model_dump() for line in body.cart_lines],
        currency=body.currency,
    )
