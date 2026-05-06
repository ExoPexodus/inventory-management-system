"""Admin endpoints for WooCommerce channel management."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Channel, Product
from app.services.woocommerce_service import (
    WooCommerceAPIError, WooCommerceAuthError,
    get_woocommerce_products, import_woocommerce_catalog, push_product, test_connection,
)

router = APIRouter(
    prefix="/v1/admin/channels",
    tags=["WooCommerce Connector"],
    dependencies=[require_permission("channels:manage")],
)


class WooCommerceConnectIn(BaseModel):
    woocommerce_store_url: str
    woocommerce_consumer_key: str
    woocommerce_consumer_secret: str
    woocommerce_webhook_secret: str


class WooCommerceConnectOut(BaseModel):
    store_name: str
    store_url: str
    currency: str | None


class SyncCatalogOut(BaseModel):
    synced: int
    errors: int
    error_skus: list[str]


class ImportCatalogOut(BaseModel):
    matched: int
    created: int
    skipped: int


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Operator not assigned to a tenant")
    return ctx.tenant_id


def _get_channel_or_404(db: Session, channel_id: UUID, tenant_id: UUID) -> Channel:
    ch = db.get(Channel, channel_id)
    if ch is None or ch.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Channel not found")
    return ch


@router.post("/{channel_id}/woocommerce/connect", response_model=WooCommerceConnectOut)
def connect_woocommerce(
    channel_id: UUID,
    body: WooCommerceConnectIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> WooCommerceConnectOut:
    tenant_id = _require_tenant(ctx)
    channel = _get_channel_or_404(db, channel_id, tenant_id)

    channel.config = {
        "woocommerce_store_url": body.woocommerce_store_url.rstrip("/"),
        "woocommerce_consumer_key": body.woocommerce_consumer_key.strip(),
        "woocommerce_consumer_secret": body.woocommerce_consumer_secret.strip(),
        "woocommerce_webhook_secret": body.woocommerce_webhook_secret.strip(),
    }
    db.flush()

    try:
        conn_result = test_connection(channel)
    except WooCommerceAuthError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Invalid credentials: {exc}")
    except WooCommerceAPIError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc))

    channel.type = "woocommerce"
    db.commit()
    return WooCommerceConnectOut(
        store_name=conn_result["store_name"],
        store_url=body.woocommerce_store_url.rstrip("/"),
        currency=conn_result.get("currency"),
    )


@router.post("/{channel_id}/woocommerce/sync-catalog", response_model=SyncCatalogOut)
def sync_catalog(
    channel_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> SyncCatalogOut:
    tenant_id = _require_tenant(ctx)
    channel = _get_channel_or_404(db, channel_id, tenant_id)
    products = db.execute(
        select(Product).where(Product.tenant_id == tenant_id, Product.status == "active")
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


@router.post("/{channel_id}/woocommerce/import-catalog", response_model=ImportCatalogOut)
def import_catalog(
    channel_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ImportCatalogOut:
    tenant_id = _require_tenant(ctx)
    channel = _get_channel_or_404(db, channel_id, tenant_id)
    try:
        woo_products = get_woocommerce_products(channel)
    except WooCommerceAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    result = import_woocommerce_catalog(db, channel, woo_products)
    db.commit()
    return ImportCatalogOut(**result)
