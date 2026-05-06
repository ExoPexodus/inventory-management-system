"""WooCommerce REST API v3 service layer.

Auth: HTTP Basic with consumer_key:consumer_secret.
Stock updated inline on product (manage_stock + stock_quantity).
Channel.config keys: woocommerce_store_url, woocommerce_consumer_key,
woocommerce_consumer_secret, woocommerce_webhook_secret.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.money import round_half_up_cents
from app.models import Channel, ChannelProductMapping, Product

logger = logging.getLogger(__name__)


class WooCommerceAuthError(Exception):
    pass


class WooCommerceAPIError(Exception):
    pass


def _base_url(channel: Channel) -> str:
    return channel.config["woocommerce_store_url"].rstrip("/") + "/wp-json/wc/v3"


def _auth(channel: Channel) -> tuple[str, str]:
    return (channel.config["woocommerce_consumer_key"],
            channel.config["woocommerce_consumer_secret"])


def test_connection(channel: Channel) -> dict[str, Any]:
    resp = httpx.get(f"{_base_url(channel)}/system_status", auth=_auth(channel), timeout=10.0)
    if resp.status_code == 401:
        raise WooCommerceAuthError(f"Invalid credentials for {channel.config['woocommerce_store_url']}")
    if resp.status_code != 200:
        raise WooCommerceAPIError(f"WooCommerce returned {resp.status_code}: {resp.text}")
    data = resp.json()
    return {"success": True, "store_name": data.get("store_name", ""),
            "currency": data.get("currency", "")}


def push_product(db: Session, channel: Channel, product: Product) -> ChannelProductMapping:
    mapping = db.execute(
        select(ChannelProductMapping).where(
            ChannelProductMapping.channel_id == channel.id,
            ChannelProductMapping.product_id == product.id,
        )
    ).scalar_one_or_none()

    price_str = f"{product.unit_price_cents / 100:.2f}"
    woo_product = {
        "name": product.name,
        "description": product.description or "",
        "sku": product.sku,
        "regular_price": price_str,
        "status": "publish" if product.status == "active" else "draft",
        "virtual": product.product_type in ("digital", "service", "donation"),
        "downloadable": product.product_type == "digital",
        "tax_status": "none" if product.product_type == "donation" else "taxable",
        "manage_stock": product.track_quantity and product.product_type == "physical",
    }

    if mapping is not None:
        url = f"{_base_url(channel)}/products/{mapping.external_product_id}"
        resp = httpx.put(url, auth=_auth(channel), content=json.dumps(woo_product),
                         headers={"Content-Type": "application/json"}, timeout=15.0)
    else:
        url = f"{_base_url(channel)}/products"
        resp = httpx.post(url, auth=_auth(channel), content=json.dumps(woo_product),
                          headers={"Content-Type": "application/json"}, timeout=15.0)

    if resp.status_code not in (200, 201):
        raise WooCommerceAPIError(
            f"Failed to push product {product.sku}: HTTP {resp.status_code}: {resp.text}"
        )

    ext_id = str(resp.json()["id"])
    now = datetime.now(UTC)

    if mapping is not None:
        mapping.external_product_id = ext_id
        mapping.synced_at = now
    else:
        mapping = ChannelProductMapping(
            tenant_id=channel.tenant_id, channel_id=channel.id,
            product_id=product.id, external_product_id=ext_id, synced_at=now,
        )
        db.add(mapping)
    db.flush()
    return mapping


def get_woocommerce_products(channel: Channel, per_page: int = 100) -> list[dict[str, Any]]:
    resp = httpx.get(f"{_base_url(channel)}/products", auth=_auth(channel),
                     params={"per_page": per_page, "status": "publish"}, timeout=30.0)
    if resp.status_code != 200:
        raise WooCommerceAPIError(f"Failed to fetch products: HTTP {resp.status_code}: {resp.text}")
    return resp.json()


def verify_webhook_signature(body: bytes, wc_signature: str, webhook_secret: str) -> bool:
    expected = base64.b64encode(
        hmac.new(webhook_secret.encode(), body, hashlib.sha256).digest()
    ).decode()
    return hmac.compare_digest(expected, wc_signature)


def import_woocommerce_catalog(
    db: Session, channel: Channel, products: list[dict[str, Any]]
) -> dict[str, int]:
    matched = created = skipped = 0
    for wp in products:
        sku = (wp.get("sku") or "").strip()
        if not sku:
            skipped += 1
            continue
        existing = db.execute(
            select(ChannelProductMapping).where(
                ChannelProductMapping.channel_id == channel.id,
                ChannelProductMapping.external_product_id == str(wp["id"]),
            )
        ).scalar_one_or_none()
        if existing:
            skipped += 1
            continue
        ims_product = db.execute(
            select(Product).where(Product.tenant_id == channel.tenant_id, Product.sku == sku)
        ).scalar_one_or_none()
        if ims_product is None:
            try:
                price_cents = round_half_up_cents(float(wp.get("price") or wp.get("regular_price", "0")) * 100)
            except (ValueError, TypeError):
                price_cents = 0
            ims_product = Product(
                tenant_id=channel.tenant_id, sku=sku,
                name=wp.get("name", sku), unit_price_cents=price_cents,
                product_type="physical", status="active",
            )
            db.add(ims_product)
            db.flush()
            created += 1
        else:
            matched += 1
        db.add(ChannelProductMapping(
            tenant_id=channel.tenant_id, channel_id=channel.id,
            product_id=ims_product.id, external_product_id=str(wp["id"]),
        ))
        db.flush()
    return {"matched": matched, "created": created, "skipped": skipped}
