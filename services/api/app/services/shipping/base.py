"""Generic shipping provider interface.

Adding a new carrier = implementing ShippingProvider and registering in registry.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass
class ShipmentResult:
    """Returned by create_shipment on success."""
    awb_code: str
    tracking_url: str
    carrier_name: str
    provider_order_id: str
    label_url: str = ""
    estimated_delivery: datetime | None = None


@dataclass
class TrackingInfo:
    """Current tracking state for a shipment."""
    awb_code: str
    status: str
    carrier_name: str
    tracking_url: str
    events: list[dict] = field(default_factory=list)


@dataclass
class ShipmentEvent:
    """A single tracking event parsed from a webhook or tracking pull."""
    status: str
    occurred_at: datetime
    provider_event_id: str
    location: str = ""
    description: str = ""
    raw_payload: dict = field(default_factory=dict)


class ShippingProviderError(Exception):
    """Raised when the carrier API returns an error."""


class ShippingNotConfiguredError(Exception):
    """Raised when the channel has no shipping provider configured."""


@runtime_checkable
class ShippingProvider(Protocol):
    """Protocol all carrier implementations must satisfy."""

    def create_shipment(self, order: object, config: dict) -> ShipmentResult: ...
    def cancel_shipment(self, awb_code: str, config: dict) -> bool: ...
    def get_tracking(self, awb_code: str, config: dict) -> TrackingInfo: ...
    def verify_webhook(self, body: bytes, headers: dict, config: dict) -> bool: ...
    def parse_webhook(self, payload: dict) -> list[ShipmentEvent]: ...
