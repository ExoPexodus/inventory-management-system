"""Admin shop CRUD endpoints."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, AdminContext, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Shop
from app.services.audit_service import write_audit

router = APIRouter(prefix="/v1/admin/shops", tags=["Admin Shops"])


def _require_tenant(ctx: AdminContext) -> UUID:
    if ctx.is_legacy_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Legacy admin token is not allowed for this endpoint",
        )
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator account has no tenant assigned",
        )
    return ctx.tenant_id


class ShopOut(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    default_tax_rate_bps: int
    auto_resolve_shortage_cents_override: int | None
    auto_resolve_overage_cents_override: int | None


class PatchShopBody(BaseModel):
    name: str | None = None
    default_tax_rate_bps: int | None = Field(default=None, ge=0)
    auto_resolve_shortage_cents_override: int | None = Field(default=None, ge=0)
    auto_resolve_overage_cents_override: int | None = Field(default=None, ge=0)

    model_config = {"extra": "forbid"}


def _to_out(shop: Shop) -> ShopOut:
    return ShopOut(
        id=shop.id,
        tenant_id=shop.tenant_id,
        name=shop.name,
        default_tax_rate_bps=shop.default_tax_rate_bps,
        auto_resolve_shortage_cents_override=shop.auto_resolve_shortage_cents_override,
        auto_resolve_overage_cents_override=shop.auto_resolve_overage_cents_override,
    )


@router.get(
    "/{shop_id}",
    response_model=ShopOut,
    dependencies=[require_permission("shops:read")],
)
def get_shop(
    shop_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ShopOut:
    tenant_id = _require_tenant(ctx)
    shop = db.get(Shop, shop_id)
    if shop is None or shop.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
    return _to_out(shop)


@router.patch(
    "/{shop_id}",
    response_model=ShopOut,
    dependencies=[require_permission("shops:write")],
)
def patch_shop(
    shop_id: UUID,
    body: PatchShopBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ShopOut:
    tenant_id = _require_tenant(ctx)
    shop = db.get(Shop, shop_id)
    if shop is None or shop.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")

    # Only apply fields the caller actually sent (distinguishes unset from null)
    sent = body.model_fields_set
    patch_data = body.model_dump(include=sent)
    for field, value in patch_data.items():
        setattr(shop, field, value)

    write_audit(
        db,
        tenant_id=tenant_id,
        operator_id=ctx.operator_id,
        action="update_shop",
        resource_type="shop",
        resource_id=str(shop_id),
    )
    db.commit()
    db.refresh(shop)

    return _to_out(shop)
