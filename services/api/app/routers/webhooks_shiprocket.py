"""Shiprocket inbound webhook receiver.

Endpoint: POST /v1/webhooks/shiprocket/{channel_id}

Authentication: X-Api-Key header must match channel.config.shiprocket_webhook_secret.
Register this URL in Shiprocket Dashboard → Settings → API → Webhooks.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Channel, Order, ShipmentEvent

router = APIRouter(prefix="/v1/webhooks/shiprocket", tags=["Shiprocket Webhooks"])
logger = logging.getLogger(__name__)


@router.post("/{channel_id}", status_code=200)
async def receive_webhook(
    channel_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    x_api_key: Annotated[str | None, Header(alias="X-Api-Key")] = None,
) -> dict:
    body = await request.body()

    channel = db.get(Channel, channel_id)
    if channel is None or channel.config.get("shipping_provider") != "shiprocket":
        raise HTTPException(status_code=404, detail="Channel not found or not Shiprocket")

    # Verify shared secret
    from app.services.shipping.shiprocket.provider import ShiprocketProvider
    provider = ShiprocketProvider()
    if not provider.verify_webhook(body, {"x-api-key": x_api_key or ""}, channel.config):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    awb_code = payload.get("awb", payload.get("awb_code", "")).strip()
    if not awb_code:
        return {"status": "ignored", "reason": "no awb_code in payload"}

    # Resolve order by AWB code (within this tenant)
    order = db.execute(
        select(Order).where(
            Order.awb_code == awb_code,
            Order.tenant_id == channel.tenant_id,
        )
    ).scalar_one_or_none()

    if order is None:
        logger.debug("Shiprocket webhook: AWB %s not found for tenant %s",
                     awb_code, channel.tenant_id)
        return {"status": "ignored", "reason": "awb_code not matched to any order"}

    # Parse events from the webhook payload
    events = provider.parse_webhook(payload)
    applied = 0

    for ev in events:
        try:
            with db.begin_nested():
                db.add(ShipmentEvent(
                    tenant_id=channel.tenant_id,
                    order_id=order.id,
                    status=ev.status,
                    occurred_at=ev.occurred_at,
                    provider_event_id=ev.provider_event_id,
                    location=ev.location,
                    description=ev.description,
                    raw_payload=ev.raw_payload,
                ))
            applied += 1
        except IntegrityError:
            logger.debug("Duplicate shipment event %s — skipping", ev.provider_event_id)
            continue

        # Update order status (latest event wins)
        order.fulfillment_status = ev.status
        if ev.status == "shipped" and order.shipped_at is None:
            order.shipped_at = ev.occurred_at
        if ev.status == "delivered":
            order.delivered_at = ev.occurred_at

    db.commit()

    # Fire outbound order.shipped webhook on delivery
    if any(ev.status == "delivered" for ev in events):
        try:
            from app.services.webhook_service import fire_event
            fire_event(db, channel.tenant_id, "order.shipped", {
                "order_id": str(order.id),
                "awb_code": awb_code,
                "status": "delivered",
                "tracking_url": order.tracking_url or "",
            })
        except Exception:
            logger.warning("Failed to fire order.shipped webhook", exc_info=True)

    logger.info("Shiprocket webhook: AWB=%s status=%s order=%s applied=%d",
                awb_code, events[-1].status if events else "?", order.id, applied)
    return {"status": "ok", "events_applied": applied, "order_id": str(order.id)}
