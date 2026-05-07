"""Provider registry — maps name strings to provider instances."""
from __future__ import annotations

from app.services.shipping.base import ShippingNotConfiguredError


def get_provider(name: str):
    if name == "shiprocket":
        from app.services.shipping.shiprocket.provider import ShiprocketProvider
        return ShiprocketProvider()
    raise ShippingNotConfiguredError(f"Unknown shipping provider: {name!r}")


def get_channel_provider(channel) -> tuple:
    """Return (provider, config) for a channel, or raise ShippingNotConfiguredError."""
    provider_name = (channel.config or {}).get("shipping_provider", "")
    if not provider_name:
        raise ShippingNotConfiguredError(
            f"Channel {channel.id} has no shipping provider configured"
        )
    return get_provider(provider_name), channel.config or {}
