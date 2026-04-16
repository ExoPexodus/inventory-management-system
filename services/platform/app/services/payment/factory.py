"""Payment gateway factory — selects the right adapter based on name and region.

Gateway configs are stored in the payment_gateway_configs table.
For development, falls back to manual gateway if no config is found.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tables import PaymentGatewayConfig
from app.services.payment.base import PaymentGateway
from app.services.payment.manual_gw import ManualGateway

logger = logging.getLogger(__name__)

# Region → default gateway mapping
REGION_DEFAULT_GATEWAY: dict[str, str] = {
    "in": "razorpay",
    "us": "stripe",
    "ca": "stripe",
    "sea": "razorpay",  # fallback to razorpay for SEA until xendit is added
}


def get_gateway(db: Session, gateway_name: str | None = None, region: str = "in") -> PaymentGateway:
    """Get a payment gateway adapter.

    If gateway_name is None, selects based on region default.
    Falls back to ManualGateway if the gateway isn't configured or SDK unavailable.
    """
    name = gateway_name or REGION_DEFAULT_GATEWAY.get(region, "manual")

    if name == "manual":
        return ManualGateway()

    # Look up config from DB
    config_row = db.execute(
        select(PaymentGatewayConfig).where(
            PaymentGatewayConfig.gateway == name,
            PaymentGatewayConfig.region == region,
            PaymentGatewayConfig.is_active.is_(True),
        )
    ).scalar_one_or_none()

    if config_row is None:
        logger.warning("No active config for gateway=%s region=%s, falling back to manual", name, region)
        return ManualGateway()

    config = config_row.config_encrypted  # In production, decrypt this

    if name == "razorpay":
        from app.services.payment.razorpay_gw import RazorpayGateway
        return RazorpayGateway(
            key_id=config.get("key_id", ""),
            key_secret=config.get("key_secret", ""),
            webhook_secret=config.get("webhook_secret"),
        )
    elif name == "stripe":
        from app.services.payment.stripe_gw import StripeGateway
        return StripeGateway(
            api_key=config.get("api_key", ""),
            webhook_secret=config.get("webhook_secret"),
        )
    else:
        logger.warning("Unknown gateway '%s', falling back to manual", name)
        return ManualGateway()


def get_gateway_for_tenant(db: Session, tenant_region: str) -> tuple[PaymentGateway, str]:
    """Get the appropriate gateway for a tenant's region. Returns (gateway, gateway_name)."""
    name = REGION_DEFAULT_GATEWAY.get(tenant_region, "manual")
    gateway = get_gateway(db, gateway_name=name, region=tenant_region)
    # If we fell back to manual, reflect that
    if isinstance(gateway, ManualGateway) and name != "manual":
        return gateway, "manual"
    return gateway, name
