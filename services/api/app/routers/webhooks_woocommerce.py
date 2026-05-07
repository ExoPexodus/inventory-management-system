"""WooCommerce webhook receiver."""
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
from app.services.woocommerce_service import verify_webhook_signature

router = APIRouter(prefix="/v1/webhooks/woocommerce", tags=["WooCommerce Webhooks"])
logger = logging.getLogger(__name__)


@router.post("/{channel_id}", status_code=200)
async def receive_webhook(
    channel_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    x_wc_webhook_signature: Annotated[str | None, Header()] = None,
    x_wc_webhook_topic: Annotated[str | None, Header()] = None,
) -> dict:
    body = await request.body()

    channel = db.get(Channel, channel_id)
    if channel is None or channel.type != "woocommerce":
        raise HTTPException(status_code=404, detail="Channel not found")

    webhook_secret = channel.config.get("woocommerce_webhook_secret", "")
    if not x_wc_webhook_signature or not verify_webhook_signature(
        body, x_wc_webhook_signature, webhook_secret
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if not x_wc_webhook_topic:
        return {"status": "ignored"}

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    topic = x_wc_webhook_topic.lower()
    if topic == "order.created":
        _handle_order_created(db, channel, payload)
    elif topic == "order.updated":
        _handle_order_updated(db, channel, payload)
    else:
        logger.debug("Unhandled WooCommerce topic: %s", topic)

    return {"status": "ok", "topic": topic}


def _handle_order_created(db: Session, channel: Channel, payload: dict) -> None:
    external_id = str(payload["id"])
    if db.execute(
        select(Order).where(Order.channel_id == channel.id, Order.external_id == external_id)
    ).scalar_one_or_none():
        return

    def _cents(s: str) -> int:
        try:
            return round(float(s) * 100)
        except (ValueError, TypeError):
            return 0

    billing = payload.get("billing", {})
    customer_email = billing.get("email")
    customer_id = None
    if customer_email:
        name = f"{billing.get('first_name', '')} {billing.get('last_name', '')}".strip()
        cust = resolve_or_create_customer(
            db, channel.tenant_id, channel.id, email=customer_email, name=name,
        )
        if cust:
            customer_id = cust.id

    shipping = payload.get("shipping", {})
    order = Order(
        tenant_id=channel.tenant_id,
        channel_id=channel.id,
        external_id=external_id,
        status="confirmed",
        customer_id=customer_id,
        customer_email=customer_email,
        subtotal_cents=_cents(payload.get("subtotal", "0")),
        tax_cents=_cents(payload.get("total_tax", "0")),
        shipping_cents=_cents(payload.get("shipping_total", "0")),
        discount_cents=0,
        total_cents=_cents(payload.get("total", "0")),
        currency_code=payload.get("currency", channel.currency_code),
        shipping_address={
            "address_1": shipping.get("address_1"), "city": shipping.get("city"),
            "country": shipping.get("country"),
        } if shipping else None,
        raw_payload=payload,
    )
    db.add(order)
    db.flush()

    for line in payload.get("line_items", []):
        sku = (line.get("sku") or "").strip()
        product_id = None
        if sku:
            from app.models import Product
            p = db.execute(
                select(Product).where(Product.tenant_id == channel.tenant_id, Product.sku == sku)
            ).scalar_one_or_none()
            if p:
                product_id = p.id

        qty = line.get("quantity", 1)
        line_total = _cents(line.get("total", "0"))
        db.add(OrderLine(
            tenant_id=channel.tenant_id, order_id=order.id, product_id=product_id,
            title=line.get("name", ""), sku=sku or None, quantity=qty,
            unit_price_cents=line_total // max(qty, 1), line_total_cents=line_total,
        ))

    db.commit()

    from app.services.email_service import send_order_confirmation
    send_order_confirmation(db, order)

    from app.services.webhook_service import build_order_confirmed_payload, fire_event
    fire_event(db, channel.tenant_id, "order.confirmed",
               build_order_confirmed_payload(db, order))

    # Enqueue shipping dispatch if channel has a provider configured
    try:
        from app.services.shipping.registry import get_channel_provider
        from app.services.shipping.base import ShippingNotConfiguredError
        get_channel_provider(channel)
        from app.worker.queue import task_queue
        task_queue().enqueue(
            "app.worker.tasks.dispatch_shipment",
            str(order.id),
            job_timeout=120,
        )
    except ShippingNotConfiguredError:
        pass  # No shipping provider configured — skip silently
    except Exception:
        import logging as _log
        _log.getLogger(__name__).warning(
            "Failed to enqueue dispatch for order %s", order.id, exc_info=True
        )


def _handle_order_updated(db: Session, channel: Channel, payload: dict) -> None:
    order = db.execute(
        select(Order).where(
            Order.channel_id == channel.id, Order.external_id == str(payload["id"])
        )
    ).scalar_one_or_none()
    if order is None:
        return
    status_map = {"completed": "fulfilled", "refunded": "refunded",
                  "cancelled": "cancelled", "processing": "confirmed", "pending": "pending"}
    wc_status = payload.get("status", "")
    if wc_status in status_map:
        order.status = status_map[wc_status]
    db.commit()
