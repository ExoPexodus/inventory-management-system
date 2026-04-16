"""Razorpay payment gateway adapter.

Primary gateway for India — supports UPI, net banking, cards, wallets.
Docs: https://razorpay.com/docs/api/
"""

from __future__ import annotations

import hashlib
import hmac
import logging

import razorpay

from app.services.payment.base import OrderResult, PaymentGateway, RefundResult, VerifyResult

logger = logging.getLogger(__name__)


class RazorpayGateway(PaymentGateway):
    def __init__(self, key_id: str, key_secret: str, webhook_secret: str | None = None):
        self._client = razorpay.Client(auth=(key_id, key_secret))
        self._key_secret = key_secret
        self._webhook_secret = webhook_secret or key_secret

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
        # Razorpay expects amount in smallest currency unit (paise for INR)
        data = {
            "amount": amount_cents,
            "currency": currency_code.upper(),
            "notes": {
                "tenant_id": tenant_id,
                "subscription_id": subscription_id,
                "description": description,
                **(metadata or {}),
            },
        }
        order = self._client.order.create(data=data)
        logger.info("Razorpay order created: %s for %s %s", order["id"], currency_code, amount_cents)
        return OrderResult(
            gateway_order_id=order["id"],
            amount_cents=order["amount"],
            currency_code=order["currency"],
            metadata={"razorpay_order": order},
        )

    def verify_payment(
        self,
        *,
        gateway_order_id: str,
        gateway_payment_id: str,
        gateway_signature: str | None = None,
    ) -> VerifyResult:
        if gateway_signature:
            # Verify Razorpay signature: HMAC-SHA256(order_id|payment_id, key_secret)
            message = f"{gateway_order_id}|{gateway_payment_id}"
            expected = hmac.new(
                self._key_secret.encode(), message.encode(), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(expected, gateway_signature):
                return VerifyResult(success=False, gateway_payment_id=gateway_payment_id)

        # Fetch payment details from Razorpay
        payment = self._client.payment.fetch(gateway_payment_id)
        success = payment.get("status") == "captured"
        return VerifyResult(
            success=success,
            gateway_payment_id=gateway_payment_id,
            method=payment.get("method"),
            metadata={"razorpay_payment": payment},
        )

    def process_refund(
        self,
        *,
        gateway_payment_id: str,
        amount_cents: int,
    ) -> RefundResult:
        refund = self._client.payment.refund(gateway_payment_id, amount_cents)
        return RefundResult(
            success=refund.get("status") in ("processed", "created"),
            refund_id=refund.get("id", ""),
            amount_cents=refund.get("amount", amount_cents),
            metadata={"razorpay_refund": refund},
        )

    def verify_webhook_signature(self, *, payload: bytes, headers: dict[str, str]) -> bool:
        signature = headers.get("x-razorpay-signature", "")
        expected = hmac.new(
            self._webhook_secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
