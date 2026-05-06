"""Shopify Admin REST API service layer.

All HTTP via httpx (synchronous). Shopify API version: 2024-10.
Channel.config keys: shopify_shop_domain, shopify_access_token,
shopify_api_secret, shopify_location_id.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.money import round_half_up_cents
from app.models import Channel, ChannelProductMapping, Product

logger = logging.getLogger(__name__)

API_VERSION = "2024-10"


class ShopifyAuthError(Exception):
    """Invalid credentials or insufficient permissions."""


class ShopifyAPIError(Exception):
    """Shopify returned an unexpected error."""


def _base_url(channel: Channel) -> str:
    domain = channel.config["shopify_shop_domain"]
    return f"https://{domain}/admin/api/{API_VERSION}"


def _headers(channel: Channel) -> dict[str, str]:
    return {
        "X-Shopify-Access-Token": channel.config["shopify_access_token"],
        "Content-Type": "application/json",
    }


def test_connection(channel: Channel) -> dict[str, Any]:
    url = f"{_base_url(channel)}/shop.json"
    resp = httpx.get(url, headers=_headers(channel), timeout=10.0)
    if resp.status_code == 401:
        raise ShopifyAuthError(f"Invalid credentials for {channel.config['shopify_shop_domain']}")
    if resp.status_code != 200:
        raise ShopifyAPIError(f"Shopify returned {resp.status_code}: {resp.text}")
    shop = resp.json()["shop"]
    return {"success": True, "shop_name": shop["name"], "currency": shop.get("currency")}


def push_product(db: Session, channel: Channel, product: Product) -> ChannelProductMapping:
    mapping = db.execute(
        select(ChannelProductMapping).where(
            ChannelProductMapping.channel_id == channel.id,
            ChannelProductMapping.product_id == product.id,
        )
    ).scalar_one_or_none()

    price_str = f"{product.unit_price_cents / 100:.2f}"
    shopify_product = {
        "title": product.name,
        "body_html": product.description or "",
        "status": "active" if product.status == "active" else "draft",
        "variants": [
            {
                "sku": product.sku,
                "price": price_str,
                "inventory_management": "shopify"
                if (product.track_quantity and product.product_type == "physical")
                else None,
                "requires_shipping": product.product_type == "physical",
                "taxable": product.product_type != "donation",
            }
        ],
    }

    if mapping is not None:
        url = f"{_base_url(channel)}/products/{mapping.external_product_id}.json"
        resp = httpx.put(url, headers=_headers(channel),
                         content=json.dumps({"product": shopify_product}),
                         timeout=15.0)
    else:
        url = f"{_base_url(channel)}/products.json"
        resp = httpx.post(url, headers=_headers(channel),
                          content=json.dumps({"product": shopify_product}),
                          timeout=15.0)

    if resp.status_code not in (200, 201):
        raise ShopifyAPIError(
            f"Failed to push product {product.sku}: HTTP {resp.status_code}: {resp.text}"
        )

    data = resp.json()["product"]
    ext_id = str(data["id"])
    ext_variant_id = str(data["variants"][0]["id"]) if data.get("variants") else None
    now = datetime.now(UTC)

    if mapping is not None:
        mapping.external_product_id = ext_id
        mapping.external_variant_id = ext_variant_id
        mapping.synced_at = now
    else:
        mapping = ChannelProductMapping(
            tenant_id=channel.tenant_id,
            channel_id=channel.id,
            product_id=product.id,
            external_product_id=ext_id,
            external_variant_id=ext_variant_id,
            synced_at=now,
        )
        db.add(mapping)
    db.flush()
    return mapping


def push_inventory_level(channel: Channel, inventory_item_id: str, quantity: int) -> None:
    location_id = int(channel.config["shopify_location_id"])
    url = f"{_base_url(channel)}/inventory_levels/set.json"
    body = json.dumps({
        "location_id": location_id,
        "inventory_item_id": inventory_item_id,
        "available": quantity,
    })
    resp = httpx.post(url, headers=_headers(channel), content=body, timeout=15.0)
    if resp.status_code != 200:
        logger.warning("Failed to push inventory level: HTTP %d: %s",
                       resp.status_code, resp.text)


def get_shopify_products(channel: Channel, limit: int = 250) -> list[dict[str, Any]]:
    url = f"{_base_url(channel)}/products.json"
    resp = httpx.get(url, headers=_headers(channel), params={"limit": limit}, timeout=30.0)
    if resp.status_code != 200:
        raise ShopifyAPIError(f"Failed to fetch products: HTTP {resp.status_code}: {resp.text}")
    return resp.json().get("products", [])


def get_shopify_locations(channel: Channel) -> list[dict[str, Any]]:
    url = f"{_base_url(channel)}/locations.json"
    resp = httpx.get(url, headers=_headers(channel), timeout=10.0)
    if resp.status_code != 200:
        raise ShopifyAPIError(f"Failed to fetch locations: HTTP {resp.status_code}")
    return resp.json().get("locations", [])


def import_shopify_catalog(
    db: Session, channel: Channel, products: list[dict[str, Any]]
) -> dict[str, int]:
    matched = created = skipped = 0
    for sp in products:
        variants = sp.get("variants", [])
        if not variants:
            skipped += 1
            continue
        variant = variants[0]
        sku = variant.get("sku", "").strip()
        if not sku:
            skipped += 1
            continue

        existing_mapping = db.execute(
            select(ChannelProductMapping).where(
                ChannelProductMapping.channel_id == channel.id,
                ChannelProductMapping.external_product_id == str(sp["id"]),
            )
        ).scalar_one_or_none()
        if existing_mapping:
            skipped += 1
            continue

        ims_product = db.execute(
            select(Product).where(
                Product.tenant_id == channel.tenant_id,
                Product.sku == sku,
            )
        ).scalar_one_or_none()

        if ims_product is None:
            price_str = variant.get("price", "0")
            try:
                price_cents = round_half_up_cents(float(price_str) * 100)
            except (ValueError, TypeError):
                price_cents = 0
            ims_product = Product(
                tenant_id=channel.tenant_id,
                sku=sku,
                name=sp.get("title", sku),
                unit_price_cents=price_cents,
                product_type="physical",
                status="active",
            )
            db.add(ims_product)
            db.flush()
            created += 1
        else:
            matched += 1

        db.add(ChannelProductMapping(
            tenant_id=channel.tenant_id,
            channel_id=channel.id,
            product_id=ims_product.id,
            external_product_id=str(sp["id"]),
            external_variant_id=str(variant["id"]) if variant.get("id") else None,
        ))
        db.flush()

    return {"matched": matched, "created": created, "skipped": skipped}


def verify_webhook_signature(body: bytes, shopify_hmac_header: str, api_secret: str) -> bool:
    expected = base64.b64encode(
        hmac.new(api_secret.encode(), body, hashlib.sha256).digest()
    ).decode()
    return hmac.compare_digest(expected, shopify_hmac_header)
