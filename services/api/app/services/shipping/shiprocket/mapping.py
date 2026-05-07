"""Maps IMS Order → Shiprocket payload and Shiprocket status → IMS status."""
from __future__ import annotations

SHIPROCKET_STATUS_MAP: dict[str, str] = {
    "new": "processing",
    "pickup pending": "processing",
    "pickup queued": "processing",
    "pickup scheduled": "processing",
    "out for pickup": "processing",
    "picked up": "processing",
    "in transit": "shipped",
    "shipment delayed": "shipped",
    "out for delivery": "out_for_delivery",
    "delivered": "delivered",
    "rto initiated": "returned",
    "rto delivered": "returned",
    "cancelled": "cancelled",
    "lost": "failed",
    "undelivered": "failed",
}


def map_status(shiprocket_status: str) -> str:
    return SHIPROCKET_STATUS_MAP.get(shiprocket_status.lower(), "processing")


def order_to_shiprocket(order, lines: list, config: dict) -> dict:
    addr = order.shipping_address or {}
    pickup_location = config.get("shiprocket_pickup_location", "Primary")
    shiprocket_channel_id = config.get("shiprocket_channel_id", "")

    payload: dict = {
        "order_id": str(order.id),
        "order_date": order.placed_at.strftime("%Y-%m-%d %H:%M"),
        "pickup_location": pickup_location,
        "billing_customer_name": (
            addr.get("first_name") or
            (order.customer_email or "").split("@")[0] or "Customer"
        ),
        "billing_last_name": addr.get("last_name", ""),
        "billing_address": addr.get("address_1") or addr.get("address", ""),
        "billing_address_2": addr.get("address_2", ""),
        "billing_city": addr.get("city", ""),
        "billing_pincode": (
            addr.get("zip") or addr.get("postcode") or addr.get("pincode", "110001")
        ),
        "billing_state": addr.get("state", ""),
        "billing_country": addr.get("country", "India"),
        "billing_phone": order.customer_phone or addr.get("phone", "9999999999"),
        "billing_email": order.customer_email or "",
        "shipping_is_billing": True,
        "payment_method": "Prepaid",
        "sub_total": order.total_cents / 100,
        "length": 10,
        "breadth": 10,
        "height": 10,
        "weight": max(0.5, sum((ln.quantity * 0.3) for ln in lines)),
        "order_items": [
            {
                "name": ln.title,
                "sku": ln.sku or str(ln.id)[:8],
                "units": ln.quantity,
                "selling_price": ln.unit_price_cents / 100,
                "discount": 0,
                "tax": 0,
                "hsn": "",
            }
            for ln in lines
        ],
    }
    if shiprocket_channel_id:
        payload["channel_id"] = shiprocket_channel_id

    return payload
