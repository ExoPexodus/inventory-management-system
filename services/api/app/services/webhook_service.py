"""Outbound webhook delivery service.

fire_event() is the single entry point. It:
  1. Finds all active endpoints subscribed to the event type
  2. Creates a WebhookDeliveryLog row per endpoint (status=pending)
  3. Enqueues an RQ task to deliver each one asynchronously

Never raises — webhook failure must not affect order creation.

Delivery (via RQ task):
  - HMAC-SHA256 signed POST to the endpoint URL
  - Up to MAX_ATTEMPTS retries with exponential backoff
  - Delivery log updated with status + response on each attempt
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, OrderLine, WebhookDeliveryLog, WebhookEndpoint

logger = logging.getLogger(__name__)

SUPPORTED_EVENTS = frozenset(["order.confirmed", "order.updated", "order.shipped"])
MAX_ATTEMPTS = 3
RETRY_DELAYS = [timedelta(minutes=5), timedelta(minutes=30)]  # delay before attempt 2, 3


def generate_secret() -> str:
    return secrets.token_hex(32)


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def build_order_confirmed_payload(db: Session, order: Order) -> dict[str, Any]:
    lines = db.execute(select(OrderLine).where(OrderLine.order_id == order.id)).scalars().all()
    return {
        "order_id": str(order.id),
        "channel_id": str(order.channel_id),
        "status": order.status,
        "customer_email": order.customer_email,
        "subtotal_cents": order.subtotal_cents,
        "discount_cents": order.discount_cents,
        "shipping_cents": order.shipping_cents,
        "tax_cents": order.tax_cents,
        "total_cents": order.total_cents,
        "currency": order.currency_code,
        "shipping_address": order.shipping_address,
        "lines": [
            {
                "product_id": str(line.product_id) if line.product_id else None,
                "title": line.title,
                "sku": line.sku,
                "quantity": line.quantity,
                "unit_price_cents": line.unit_price_cents,
                "line_total_cents": line.line_total_cents,
            }
            for line in lines
        ],
    }


def fire_event(
    db: Session,
    tenant_id: UUID,
    event_type: str,
    data: dict[str, Any],
) -> int:
    """Queue delivery of an event to all active subscribed endpoints.

    Returns the number of delivery logs created. Never raises.
    """
    if event_type not in SUPPORTED_EVENTS:
        logger.debug("Unknown event type %r, skipping webhook fire", event_type)
        return 0

    try:
        endpoints = db.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.tenant_id == tenant_id,
                WebhookEndpoint.status == "active",
                WebhookEndpoint.events.contains([event_type]),
            )
        ).scalars().all()
    except Exception:
        logger.warning("Failed to query webhook endpoints for tenant %s", tenant_id, exc_info=True)
        return 0

    if not endpoints:
        return 0

    now = datetime.now(UTC)
    count = 0
    for endpoint in endpoints:
        payload = {
            "id": None,  # filled in after flush
            "event": event_type,
            "created_at": now.isoformat(),
            "data": data,
        }
        try:
            log = WebhookDeliveryLog(
                tenant_id=tenant_id,
                endpoint_id=endpoint.id,
                event_type=event_type,
                payload=payload,
                status="pending",
            )
            db.add(log)
            db.flush()
            # Embed delivery ID in the payload for traceability
            log.payload = {**payload, "id": str(log.id)}
            db.flush()
            db.commit()

            _enqueue_delivery(str(log.id))
            count += 1
        except Exception:
            logger.warning(
                "Failed to create webhook delivery log for endpoint %s", endpoint.id, exc_info=True
            )

    return count


def _enqueue_delivery(delivery_log_id: str) -> None:
    try:
        from app.worker.queue import task_queue
        task_queue().enqueue(
            "app.worker.tasks.deliver_webhook",
            delivery_log_id,
            job_timeout=30,
        )
    except Exception:
        logger.warning("Failed to enqueue webhook delivery %s", delivery_log_id, exc_info=True)


def _execute_delivery(db: Session, delivery_log_id: str) -> str:
    """Inner delivery logic using an existing session. Called by deliver_webhook_sync and tests."""
    try:
        log = db.get(WebhookDeliveryLog, delivery_log_id)
        if log is None:
            return "not_found"

        endpoint = db.get(WebhookEndpoint, log.endpoint_id)
        if endpoint is None or endpoint.status != "active":
            log.status = "failed"
            log.response_body = "Endpoint no longer active"
            db.commit()
            return "failed"

        body = json.dumps(log.payload, default=str).encode()
        sig = _sign(endpoint.secret, body)

        log.attempt_count += 1
        try:
            resp = httpx.post(
                endpoint.url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-IMS-Signature": sig,
                    "X-IMS-Event": log.event_type,
                    "X-IMS-Delivery": str(log.id),
                },
                timeout=10.0,
            )
            log.response_status = resp.status_code
            log.response_body = resp.text[:500]

            if resp.status_code < 300:
                log.status = "delivered"
                log.delivered_at = datetime.now(UTC)
                db.commit()
                return "delivered"

        except Exception as exc:
            log.response_body = str(exc)[:500]

        # Delivery failed — schedule retry or mark as failed
        if log.attempt_count < MAX_ATTEMPTS:
            delay = RETRY_DELAYS[log.attempt_count - 1]
            log.next_retry_at = datetime.now(UTC) + delay
            log.status = "pending"
            db.commit()
            try:
                from app.worker.queue import task_queue
                task_queue().enqueue_at(
                    log.next_retry_at,
                    "app.worker.tasks.deliver_webhook",
                    str(log.id),
                    job_timeout=30,
                )
            except Exception:
                logger.warning("Failed to schedule retry for %s", log.id, exc_info=True)
            return "retry_scheduled"

        log.status = "failed"
        db.commit()
        logger.warning("Webhook delivery %s failed after %d attempts", log.id, log.attempt_count)
        return "failed"

    except Exception:
        logger.warning("Unexpected error delivering webhook %s", delivery_log_id, exc_info=True)
        return "error"


def deliver_webhook_sync(delivery_log_id: str) -> str:
    """RQ entry point: open a session and execute delivery."""
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        return _execute_delivery(db, delivery_log_id)
    finally:
        db.close()
