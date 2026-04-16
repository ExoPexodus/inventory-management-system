"""Manual (offline) payment gateway adapter.

Records bank transfers, cash payments, and other offline methods.
No external API calls — just local bookkeeping.
"""

from __future__ import annotations

import uuid

from app.services.payment.base import OrderResult, PaymentGateway, RefundResult, VerifyResult


class ManualGateway(PaymentGateway):
    """Pseudo-gateway for recording offline/manual payments."""

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
        return OrderResult(
            gateway_order_id=f"manual-{uuid.uuid4().hex[:12]}",
            amount_cents=amount_cents,
            currency_code=currency_code,
            metadata={"method": "manual", "description": description},
        )

    def verify_payment(
        self,
        *,
        gateway_order_id: str,
        gateway_payment_id: str,
        gateway_signature: str | None = None,
    ) -> VerifyResult:
        # Manual payments are always "verified" — the operator confirms receipt
        return VerifyResult(
            success=True,
            gateway_payment_id=gateway_payment_id or gateway_order_id,
            method="manual",
        )

    def process_refund(
        self,
        *,
        gateway_payment_id: str,
        amount_cents: int,
    ) -> RefundResult:
        return RefundResult(
            success=True,
            refund_id=f"manual-refund-{uuid.uuid4().hex[:12]}",
            amount_cents=amount_cents,
        )

    def verify_webhook_signature(self, *, payload: bytes, headers: dict[str, str]) -> bool:
        return False  # manual gateway has no webhooks
