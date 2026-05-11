"""Shiprocket ShippingProvider implementation."""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

import httpx

from app.db.rls import set_rls_context
from app.services.shipping.base import ShipmentEvent, ShipmentResult, ShippingProviderError, TrackingInfo
from app.services.shipping.shiprocket import client as sr_client
from app.services.shipping.shiprocket.mapping import (
    map_status,
    order_to_shiprocket,
    request_to_shiprocket_return,
)

logger = logging.getLogger(__name__)


class ShiprocketProvider:

    def create_shipment(self, order, config: dict) -> ShipmentResult:
        from app.db.session import SessionLocal
        from app.models import OrderLine
        from sqlalchemy import select

        channel_id = UUID(str(order.channel_id))
        db = SessionLocal()
        try:
            set_rls_context(db, is_admin=True, tenant_id=None)
            lines = db.execute(
                select(OrderLine).where(OrderLine.order_id == order.id)
            ).scalars().all()
            payload = order_to_shiprocket(order, list(lines), config)
        finally:
            db.close()

        try:
            create_resp = sr_client.api_post(channel_id, config, "/orders/create/adhoc", payload)
            sr_order_id = str(create_resp.get("order_id", ""))
            shipment_id = str(create_resp.get("shipment_id", ""))

            awb_resp = sr_client.api_post(channel_id, config, "/courier/assign/awb",
                                          {"shipment_id": shipment_id})
            awb_data = awb_resp.get("response", {}).get("data", {})
            awb_code = awb_data.get("awb_code", "")
            carrier_name = awb_data.get("courier_name", "Shiprocket Courier")

            sr_client.api_post(channel_id, config, "/courier/generate/pickup",
                               {"shipment_id": [shipment_id]})

            tracking_url = f"https://shiprocket.co/tracking/{awb_code}" if awb_code else ""

            label_url = ""
            try:
                label_resp = sr_client.api_get(
                    channel_id, config,
                    f"/courier/generate/label?shipment_id={shipment_id}"
                )
                label_url = label_resp.get("label_url", "")
            except Exception:
                logger.debug("Label generation failed for shipment %s", shipment_id)

            return ShipmentResult(
                awb_code=awb_code,
                tracking_url=tracking_url,
                carrier_name=carrier_name,
                provider_order_id=sr_order_id,
                label_url=label_url,
            )
        except httpx.HTTPStatusError as exc:
            raise ShippingProviderError(
                f"Shiprocket API error {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc

    def create_reverse_shipment(self, refund_request, order, refund_lines, tenant, config: dict) -> ShipmentResult:
        """Issue a return-pickup shipment for an approved RMA.

        Pickup is the customer's original shipping address; ship-to is the
        merchant warehouse (tenant billing address). Returns a ShipmentResult
        with the AWB code that can be stored on the RefundRequest.
        """
        channel_id = UUID(str(refund_request.channel_id)) if refund_request.channel_id else UUID(int=0)
        payload = request_to_shiprocket_return(refund_request, order, refund_lines, tenant, config)

        try:
            create_resp = sr_client.api_post(channel_id, config, "/orders/create/return", payload)
            sr_order_id = str(create_resp.get("order_id", ""))
            shipment_id = str(create_resp.get("shipment_id", ""))

            # Assign AWB on the return shipment
            awb_resp = sr_client.api_post(
                channel_id, config, "/courier/assign/awb",
                {"shipment_id": shipment_id},
            )
            awb_data = awb_resp.get("response", {}).get("data", {})
            awb_code = awb_data.get("awb_code", "")
            carrier_name = awb_data.get("courier_name", "Shiprocket Return")

            tracking_url = f"https://shiprocket.co/tracking/{awb_code}" if awb_code else ""

            return ShipmentResult(
                awb_code=awb_code,
                tracking_url=tracking_url,
                carrier_name=carrier_name,
                provider_order_id=sr_order_id,
                label_url="",
            )
        except httpx.HTTPStatusError as exc:
            raise ShippingProviderError(
                f"Shiprocket return-shipment API error {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc

    def cancel_shipment(self, awb_code: str, config: dict) -> bool:
        try:
            from app.db.session import SessionLocal
            from app.models import Order
            from sqlalchemy import select
            db = SessionLocal()
            try:
                set_rls_context(db, is_admin=True, tenant_id=None)
                order = db.execute(
                    select(Order).where(Order.awb_code == awb_code)
                ).scalar_one_or_none()
                if not order:
                    return False
                channel_id = UUID(str(order.channel_id))
                provider_order_id = order.provider_order_id or ""
            finally:
                db.close()

            sr_client.api_post(channel_id, config, "/orders/cancel",
                               {"ids": [provider_order_id]})
            return True
        except Exception:
            logger.warning("Failed to cancel shipment %s", awb_code, exc_info=True)
            return False

    def get_tracking(self, awb_code: str, config: dict) -> TrackingInfo:
        from app.db.session import SessionLocal
        from app.models import Order
        from sqlalchemy import select
        db = SessionLocal()
        try:
            set_rls_context(db, is_admin=True, tenant_id=None)
            order = db.execute(
                select(Order).where(Order.awb_code == awb_code)
            ).scalar_one_or_none()
            channel_id = UUID(str(order.channel_id)) if order else UUID(int=0)
        finally:
            db.close()

        resp = sr_client.api_get(channel_id, config, f"/courier/track/awb/{awb_code}")
        tracking_data = resp.get("tracking_data", {})
        shipment_track = tracking_data.get("shipment_track", [{}])[0]
        current_status = shipment_track.get("current_status", "")

        return TrackingInfo(
            awb_code=awb_code,
            status=map_status(current_status),
            carrier_name=shipment_track.get("courier_name", ""),
            tracking_url=f"https://shiprocket.co/tracking/{awb_code}",
            events=[
                {
                    "status": e.get("status", ""),
                    "date": e.get("date", ""),
                    "location": e.get("location", ""),
                    "activity": e.get("activity", ""),
                }
                for e in tracking_data.get("shipment_track_activities", [])
            ],
        )

    def verify_webhook(self, body: bytes, headers: dict, config: dict) -> bool:
        secret = config.get("shiprocket_webhook_secret", "")
        if not secret:
            return True
        api_key = headers.get("x-api-key", headers.get("X-Api-Key", ""))
        import hmac as _hmac
        return _hmac.compare_digest(secret, api_key)

    def parse_webhook(self, payload: dict) -> list[ShipmentEvent]:
        status_str = payload.get("current_status", payload.get("status", ""))
        ims_status = map_status(status_str)

        raw_date = payload.get("updated_at") or payload.get("scan_datetime") or ""
        try:
            from dateutil.parser import parse as _parse
            occurred_at = _parse(str(raw_date)) if raw_date else datetime.now(UTC)
        except Exception:
            occurred_at = datetime.now(UTC)

        awb = payload.get("awb", payload.get("awb_code", ""))
        provider_event_id = f"{awb}:{status_str}:{raw_date}"

        return [ShipmentEvent(
            status=ims_status,
            occurred_at=occurred_at,
            provider_event_id=provider_event_id,
            location=payload.get("location", ""),
            description=status_str,
            raw_payload=payload,
        )]
