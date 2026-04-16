"""Abstract base class for payment gateway adapters.

Each gateway (Razorpay, Stripe, Manual) implements this interface.
The factory selects the right adapter based on gateway name + region.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class OrderResult:
    """Returned after creating a payment order on the gateway."""
    gateway_order_id: str
    amount_cents: int
    currency_code: str
    checkout_url: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class VerifyResult:
    """Returned after verifying a payment."""
    success: bool
    gateway_payment_id: str
    method: str | None = None  # upi, card, netbanking, etc.
    metadata: dict = field(default_factory=dict)


@dataclass
class RefundResult:
    """Returned after processing a refund."""
    success: bool
    refund_id: str
    amount_cents: int
    metadata: dict = field(default_factory=dict)


class PaymentGateway(ABC):
    """Gateway adapter interface. One implementation per payment provider."""

    @abstractmethod
    def create_order(
        self,
        amount_cents: int,
        currency_code: str,
        *,
        tenant_id: str,
        subscription_id: str,
        description: str = "",
        metadata: dict | None = None,
    ) -> OrderResult:
        """Create a payment order/session on the gateway."""
        ...

    @abstractmethod
    def verify_payment(
        self,
        *,
        gateway_order_id: str,
        gateway_payment_id: str,
        gateway_signature: str | None = None,
    ) -> VerifyResult:
        """Verify that a payment was successful (called after client-side completion or webhook)."""
        ...

    @abstractmethod
    def process_refund(
        self,
        *,
        gateway_payment_id: str,
        amount_cents: int,
    ) -> RefundResult:
        """Initiate a refund for a payment."""
        ...

    @abstractmethod
    def verify_webhook_signature(self, *, payload: bytes, headers: dict[str, str]) -> bool:
        """Verify that a webhook payload is authentic."""
        ...
