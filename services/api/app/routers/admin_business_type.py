"""Tenant business-type settings: read current type + UI feature flags, set on onboarding."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Shop, Tenant

router = APIRouter(tags=["Tenant Business Type"])

_FLAG_MAP: dict[str, dict[str, bool]] = {
    "online": {
        "show_shops_management": False,
        "show_pos_features": False,
        "show_ecommerce_features": True,
        "can_add_physical_store": True,
        "can_add_online_channel": False,
    },
    "retail": {
        "show_shops_management": True,
        "show_pos_features": True,
        "show_ecommerce_features": False,
        "can_add_physical_store": False,
        "can_add_online_channel": True,
    },
    "hybrid": {
        "show_shops_management": True,
        "show_pos_features": True,
        "show_ecommerce_features": True,
        "can_add_physical_store": True,
        "can_add_online_channel": True,
    },
}


class BusinessTypeOut(BaseModel):
    business_type: str
    show_shops_management: bool
    show_pos_features: bool
    show_ecommerce_features: bool
    can_add_physical_store: bool
    can_add_online_channel: bool


class BusinessTypeIn(BaseModel):
    business_type: str = Field(pattern="^(online|retail|hybrid)$")


class EnablePhysicalStoreIn(BaseModel):
    shop_name: str = Field(min_length=1, max_length=255)
    timezone: str | None = None


def _require_tenant(ctx: AdminAuthDep, db: Session) -> Tenant:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Operator not assigned to a tenant")
    tenant = db.get(Tenant, ctx.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


def _build_out(bt: str) -> BusinessTypeOut:
    flags = _FLAG_MAP.get(bt, _FLAG_MAP["retail"])
    return BusinessTypeOut(business_type=bt, **flags)


def _ensure_virtual_shop(db: Session, tenant: Tenant) -> None:
    existing = db.execute(
        select(Shop).where(Shop.tenant_id == tenant.id, Shop.kind == "virtual")
    ).scalar_one_or_none()
    if existing is None:
        db.add(Shop(tenant_id=tenant.id, name="Online Store", kind="virtual"))
        db.flush()


@router.get(
    "/v1/admin/tenant-settings/business-type",
    response_model=BusinessTypeOut,
    dependencies=[require_permission("business_type:manage")],
)
def get_business_type(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> BusinessTypeOut:
    tenant = _require_tenant(ctx, db)
    return _build_out(tenant.business_type)


@router.post(
    "/v1/admin/tenant-settings/business-type",
    response_model=BusinessTypeOut,
    dependencies=[require_permission("business_type:manage")],
)
def set_business_type(
    body: BusinessTypeIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> BusinessTypeOut:
    tenant = _require_tenant(ctx, db)
    if body.business_type in {"online", "hybrid"}:
        _ensure_virtual_shop(db, tenant)
    tenant.business_type = body.business_type
    db.commit()
    return _build_out(body.business_type)


@router.post(
    "/v1/admin/setup/enable-physical-store",
    response_model=BusinessTypeOut,
    dependencies=[require_permission("business_type:manage")],
)
def enable_physical_store(
    body: EnablePhysicalStoreIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> BusinessTypeOut:
    """Convert online→hybrid: create a physical shop + POS channel, flip to hybrid."""
    tenant = _require_tenant(ctx, db)

    shop = Shop(
        tenant_id=tenant.id,
        name=body.shop_name,
        kind="physical",
        timezone=body.timezone,
    )
    db.add(shop)
    db.flush()

    from app.services.channel_service import get_or_create_pos_channel
    get_or_create_pos_channel(db, shop)

    tenant.business_type = "hybrid"
    db.commit()
    return _build_out("hybrid")
