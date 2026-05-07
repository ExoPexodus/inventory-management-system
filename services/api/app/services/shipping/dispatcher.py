"""High-level dispatch — called by the RQ task and admin manual-dispatch endpoint.

Loads order + channel, calls provider.create_shipment(), persists AWB/tracking,
inserts ShipmentEvent, sends shipping notification email, fires order.shipped webhook.
Never raises — fulfillment_status = "failed" on any error.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Channel, Order, ShipmentEvent, TenantEmailConfig
from app.services.shipping.base import ShippingNotConfiguredError, ShippingProviderError
from app.services.shipping.registry import get_channel_provider

logger = logging.getLogger(__name__)


def dispatch_order(db: Session, order: Order) -> bool:
    """Dispatch one order. Returns True on success, False on failure/skip."""
    channel = db.get(Channel, order.channel_id)
    if channel is None:
        logger.warning("dispatch_order: channel %s not found", order.channel_id)
        return False

    try:
        provider, config = get_channel_provider(channel)
    except ShippingNotConfiguredError:
        logger.debug("No shipping provider for channel %s — skipping", channel.id)
        return False

    try:
        result = provider.create_shipment(order, config)
    except ShippingProviderError as exc:
        logger.warning("Shipment dispatch failed for order %s: %s", order.id, exc)
        order.fulfillment_status = "failed"
        db.add(ShipmentEvent(
            tenant_id=order.tenant_id,
            order_id=order.id,
            status="failed",
            occurred_at=datetime.now(UTC),
            provider_event_id=f"dispatch_failed:{order.id}",
            description=str(exc)[:500],
            raw_payload={"error": str(exc)},
        ))
        db.commit()
        return False
    except Exception:
        logger.exception("Unexpected error dispatching order %s", order.id)
        order.fulfillment_status = "failed"
        db.commit()
        return False

    order.fulfillment_status = "processing"
    order.shipping_provider = channel.config.get("shipping_provider", "")
    order.awb_code = result.awb_code
    order.tracking_url = result.tracking_url
    order.carrier_name = result.carrier_name
    order.provider_order_id = result.provider_order_id
    order.label_url = result.label_url

    db.add(ShipmentEvent(
        tenant_id=order.tenant_id,
        order_id=order.id,
        status="processing",
        occurred_at=datetime.now(UTC),
        provider_event_id=f"dispatch_success:{order.id}",
        description=f"Shipment created. AWB: {result.awb_code}",
        raw_payload={
            "awb_code": result.awb_code,
            "carrier_name": result.carrier_name,
            "provider_order_id": result.provider_order_id,
        },
    ))
    db.commit()

    # Shipping notification email (non-blocking)
    try:
        _send_shipping_email(db, order)
    except Exception:
        logger.warning("Failed to send shipping email for order %s", order.id, exc_info=True)

    # order.shipped outbound webhook (non-blocking)
    try:
        from app.services.webhook_service import fire_event
        fire_event(db, order.tenant_id, "order.shipped", {
            "order_id": str(order.id),
            "awb_code": result.awb_code,
            "tracking_url": result.tracking_url,
            "carrier_name": result.carrier_name,
        })
    except Exception:
        logger.warning("Failed to fire order.shipped webhook for %s", order.id, exc_info=True)

    logger.info("Order %s dispatched via %s, AWB=%s",
                order.id, channel.config.get("shipping_provider"), result.awb_code)
    return True


def _send_shipping_email(db: Session, order: Order) -> None:
    """Send a basic shipping notification. Non-critical."""
    if not order.customer_email:
        return
    from app.services.email_service import (
        decrypt_secret, _resend_send, _from_header, _send_via_smtp
    )
    config = db.execute(
        select(TenantEmailConfig).where(TenantEmailConfig.tenant_id == order.tenant_id)
    ).scalar_one_or_none()
    if not config or not config.from_email:
        return
    provider = (config.provider or "").strip().lower()
    api_key = decrypt_secret(config.api_key_encrypted)
    subject = f"Your order #{str(order.id)[:8].upper()} has been shipped"
    html = (
        f"<p>Your order has been dispatched.</p>"
        f"<p><strong>Carrier:</strong> {order.carrier_name or 'Our courier'}</p>"
        f"<p><strong>AWB:</strong> {order.awb_code or '—'}</p>"
        + (f"<p><a href='{order.tracking_url}'>Track your shipment</a></p>"
           if order.tracking_url else "")
    )
    if provider == "resend" and api_key:
        _resend_send(api_key=api_key, from_address=_from_header(config),
                     to_email=order.customer_email, subject=subject, html=html)
    elif provider == "smtp":
        _send_via_smtp(config, to_email=order.customer_email, subject=subject,
                       text_body=f"Shipped. AWB: {order.awb_code}", html_body=html)
