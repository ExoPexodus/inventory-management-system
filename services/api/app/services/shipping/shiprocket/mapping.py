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


def request_to_shiprocket_return(refund_request, order, refund_lines: list, tenant, config: dict) -> dict:
    """Build a Shiprocket return-shipment payload.

    Pickup is the customer's original shipping address (we're picking up the goods
    from them). Shipping destination is the merchant's warehouse — taken from the
    tenant's billing address.
    """
    cust_addr = order.shipping_address or {}
    customer_name = (
        cust_addr.get("first_name")
        or (order.customer_email or "").split("@")[0]
        or "Customer"
    )

    return {
        "order_id": f"RETURN-{refund_request.id}",
        "order_date": refund_request.created_at.strftime("%Y-%m-%d %H:%M"),
        "channel_id": config.get("shiprocket_channel_id", ""),
        # PICKUP = customer's original shipping address
        "pickup_customer_name": customer_name,
        "pickup_last_name": cust_addr.get("last_name", ""),
        "pickup_address": cust_addr.get("address_1") or cust_addr.get("address", ""),
        "pickup_address_2": cust_addr.get("address_2", ""),
        "pickup_city": cust_addr.get("city", ""),
        "pickup_state": cust_addr.get("state", ""),
        "pickup_country": cust_addr.get("country", "India"),
        "pickup_pincode": (
            cust_addr.get("zip") or cust_addr.get("postcode") or cust_addr.get("pincode", "110001")
        ),
        "pickup_email": order.customer_email or "",
        "pickup_phone": order.customer_phone or cust_addr.get("phone", "9999999999"),
        # SHIPPING = merchant warehouse (tenant billing address)
        "shipping_customer_name": tenant.billing_company_name or tenant.name,
        "shipping_last_name": "",
        "shipping_address": tenant.billing_address_line1 or "Warehouse",
        "shipping_address_2": tenant.billing_address_line2 or "",
        "shipping_city": tenant.billing_city or "",
        "shipping_state": tenant.billing_state or "",
        "shipping_country": tenant.billing_country or "India",
        "shipping_pincode": tenant.billing_postal_code or "110001",
        "shipping_phone": cust_addr.get("phone", "9999999999"),  # Shiprocket requires; merchant phone if available
        "order_items": [
            {
                "name": ln.product_name,
                "sku": ln.product_sku or str(ln.id)[:8],
                "units": ln.quantity_approved or ln.quantity_requested,
                "selling_price": ln.unit_price_cents / 100,
                "discount": 0,
                "qc_enable": False,
            }
            for ln in refund_lines
        ],
        "payment_method": "Prepaid",
        "total_discount": "0",
        "sub_total": (refund_request.total_refund_cents or 0) / 100,
        "length": 10,
        "breadth": 10,
        "height": 10,
        "weight": max(0.5, sum((ln.quantity_approved or ln.quantity_requested) * 0.3 for ln in refund_lines)),
    }


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
