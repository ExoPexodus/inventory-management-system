"""Shopify webhook receiver.

Endpoint: POST /v1/webhooks/shopify/{channel_id}

Verifies HMAC signature using channel's shopify_api_secret.
Supported topics: orders/create, orders/updated.

Register URLs manually in Shopify Admin → Settings → Notifications.
"""
from __future__ import annotations

import json
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Channel, Order, OrderLine
from app.services.customer_resolver import resolve_or_create_customer
from app.services.shopify_service import verify_webhook_signature

router = APIRouter(prefix="/v1/webhooks/shopify", tags=["Shopify Webhooks"])
logger = logging.getLogger(__name__)


@router.post("/{channel_id}", status_code=200)
async def receive_webhook(
    channel_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    x_shopify_hmac_sha256: Annotated[str | None, Header()] = None,
    x_shopify_topic: Annotated[str | None, Header()] = None,
) -> dict:
    body = await request.body()

    channel = db.get(Channel, channel_id)
    if channel is None or channel.type != "shopify":
        raise HTTPException(status_code=404, detail="Channel not found")

    api_secret = channel.config.get("shopify_api_secret", "")
    if not x_shopify_hmac_sha256 or not verify_webhook_signature(
        body, x_shopify_hmac_sha256, api_secret
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if not x_shopify_topic:
        return {"status": "ignored", "reason": "no topic header"}

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    topic = x_shopify_topic.lower()
    if topic == "orders/create":
        _handle_order_create(db, channel, payload)
    elif topic == "orders/updated":
        _handle_order_updated(db, channel, payload)
    else:
        logger.debug("Unhandled Shopify topic: %s", topic)

    return {"status": "ok", "topic": topic}


def _handle_order_create(db: Session, channel: Channel, payload: dict) -> None:
    external_id = str(payload["id"])

    existing = db.execute(
        select(Order).where(
            Order.channel_id == channel.id,
            Order.external_id == external_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return

    currency = payload.get("currency", channel.currency_code)

    def _cents(amount_str: str) -> int:
        try:
            return round(float(amount_str) * 100)
        except (ValueError, TypeError):
            return 0

    subtotal_cents = _cents(payload.get("subtotal_price", "0"))
    tax_cents = _cents(payload.get("total_tax", "0"))
    total_cents = _cents(payload.get("total_price", "0"))

    customer_email = None
    customer_id = None
    customer = payload.get("customer", {})
    if customer:
        customer_email = customer.get("email") or payload.get("email")
        if customer_email:
            cust = resolve_or_create_customer(
                db, channel.tenant_id, channel.id,
                email=customer_email,
                name=f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip(),
            )
            if cust:
                customer_id = cust.id

    shipping_addr = payload.get("shipping_address") or payload.get("billing_address")

    order = Order(
        tenant_id=channel.tenant_id,
        channel_id=channel.id,
        external_id=external_id,
        status="confirmed",
        customer_id=customer_id,
        customer_email=customer_email or payload.get("email"),
        subtotal_cents=subtotal_cents,
        tax_cents=tax_cents,
        shipping_cents=0,
        discount_cents=0,
        total_cents=total_cents,
        currency_code=currency,
        shipping_address=shipping_addr,
        raw_payload=payload,
    )
    db.add(order)
    db.flush()

    for line in payload.get("line_items", []):
        sku = line.get("sku", "").strip()
        product_id = None
        if sku:
            from app.models import Product
            ims_product = db.execute(
                select(Product).where(
                    Product.tenant_id == channel.tenant_id,
                    Product.sku == sku,
                )
            ).scalar_one_or_none()
            if ims_product:
                product_id = ims_product.id

        db.add(OrderLine(
            tenant_id=channel.tenant_id,
            order_id=order.id,
            product_id=product_id,
            title=line.get("title", ""),
            sku=sku or None,
            quantity=line.get("quantity", 1),
            unit_price_cents=_cents(line.get("price", "0")),
            line_total_cents=_cents(line.get("price", "0")) * line.get("quantity", 1),
        ))

    db.commit()
    logger.info("Shopify order %s ingested for channel %s", external_id, channel.id)

    from app.services.email_service import send_order_confirmation
    send_order_confirmation(db, order)

    from app.services.webhook_service import build_order_confirmed_payload, fire_event
    fire_event(db, channel.tenant_id, "order.confirmed",
               build_order_confirmed_payload(db, order))


def _handle_order_updated(db: Session, channel: Channel, payload: dict) -> None:
    external_id = str(payload["id"])
    order = db.execute(
        select(Order).where(
            Order.channel_id == channel.id,
            Order.external_id == external_id,
        )
    ).scalar_one_or_none()
    if order is None:
        return

    financial_status = payload.get("financial_status", "")
    fulfillment_status = payload.get("fulfillment_status", "")

    if financial_status in ("refunded", "voided"):
        order.status = "refunded"
    elif fulfillment_status == "fulfilled":
        order.status = "fulfilled"
    elif financial_status == "paid":
        order.status = "confirmed"

    db.commit()
