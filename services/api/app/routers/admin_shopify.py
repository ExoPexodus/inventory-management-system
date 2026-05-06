"""Admin endpoints for Shopify channel management."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Channel, ChannelProductMapping, Product
from app.services.inventory_pool_service import available_stock_for_channel
from app.services.shopify_service import (
    ShopifyAPIError, ShopifyAuthError,
    get_shopify_locations, get_shopify_products,
    import_shopify_catalog, push_inventory_level, push_product, test_connection,
)

router = APIRouter(
    prefix="/v1/admin/channels",
    tags=["Shopify Connector"],
    dependencies=[require_permission("channels:manage")],
)


class ShopifyConnectIn(BaseModel):
    shopify_shop_domain: str
    shopify_access_token: str
    shopify_api_secret: str


class ShopifyConnectOut(BaseModel):
    shop_name: str
    currency: str | None
    location_id: str
    location_name: str


class SyncCatalogOut(BaseModel):
    synced: int
    errors: int
    error_skus: list[str]


class ImportCatalogOut(BaseModel):
    matched: int
    created: int
    skipped: int


class SyncInventoryOut(BaseModel):
    synced: int
    errors: int


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Operator not assigned to a tenant")
    return ctx.tenant_id


def _get_channel_or_404(db: Session, channel_id: UUID, tenant_id: UUID) -> Channel:
    ch = db.get(Channel, channel_id)
    if ch is None or ch.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Channel not found")
    return ch


@router.post("/{channel_id}/shopify/connect", response_model=ShopifyConnectOut)
def connect_shopify(
    channel_id: UUID,
    body: ShopifyConnectIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ShopifyConnectOut:
    tenant_id = _require_tenant(ctx)
    channel = _get_channel_or_404(db, channel_id, tenant_id)

    channel.config = {
        "shopify_shop_domain": body.shopify_shop_domain.strip().lower(),
        "shopify_access_token": body.shopify_access_token.strip(),
        "shopify_api_secret": body.shopify_api_secret.strip(),
        "shopify_location_id": "",
    }
    db.flush()

    try:
        conn_result = test_connection(channel)
    except ShopifyAuthError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Invalid credentials: {exc}")
    except ShopifyAPIError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc))

    try:
        locations = get_shopify_locations(channel)
    except ShopifyAPIError:
        locations = []

    if not locations:
        db.rollback()
        raise HTTPException(status_code=502,
                            detail="Could not fetch Shopify locations. "
                                   "Ensure the access token has 'inventory' scope.")

    primary = locations[0]
    channel.config = {**channel.config, "shopify_location_id": str(primary["id"])}
    channel.type = "shopify"
    db.commit()

    return ShopifyConnectOut(
        shop_name=conn_result["shop_name"],
        currency=conn_result.get("currency"),
        location_id=str(primary["id"]),
        location_name=primary["name"],
    )


@router.post("/{channel_id}/shopify/sync-catalog", response_model=SyncCatalogOut)
def sync_catalog(
    channel_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> SyncCatalogOut:
    tenant_id = _require_tenant(ctx)
    channel = _get_channel_or_404(db, channel_id, tenant_id)

    products = db.execute(
        select(Product).where(
            Product.tenant_id == tenant_id,
            Product.status == "active",
        )
    ).scalars().all()

    synced = errors = 0
    error_skus: list[str] = []

    for product in products:
        try:
            push_product(db, channel, product)
            synced += 1
        except Exception:
            errors += 1
            error_skus.append(product.sku)

    db.commit()
    return SyncCatalogOut(synced=synced, errors=errors, error_skus=error_skus)


@router.post("/{channel_id}/shopify/sync-inventory", response_model=SyncInventoryOut)
def sync_inventory(
    channel_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> SyncInventoryOut:
    tenant_id = _require_tenant(ctx)
    channel = _get_channel_or_404(db, channel_id, tenant_id)

    mappings = db.execute(
        select(ChannelProductMapping).where(
            ChannelProductMapping.channel_id == channel_id,
            ChannelProductMapping.external_variant_id.isnot(None),
        )
    ).scalars().all()

    synced = errors = 0
    for mapping in mappings:
        try:
            qty = available_stock_for_channel(db, channel.id, mapping.product_id)
            push_inventory_level(channel, mapping.external_variant_id, qty)
            synced += 1
        except Exception:
            errors += 1

    return SyncInventoryOut(synced=synced, errors=errors)


@router.post("/{channel_id}/shopify/import-catalog", response_model=ImportCatalogOut)
def import_catalog(
    channel_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ImportCatalogOut:
    tenant_id = _require_tenant(ctx)
    channel = _get_channel_or_404(db, channel_id, tenant_id)

    try:
        shopify_products = get_shopify_products(channel)
    except ShopifyAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    result = import_shopify_catalog(db, channel, shopify_products)
    db.commit()
    return ImportCatalogOut(**result)
