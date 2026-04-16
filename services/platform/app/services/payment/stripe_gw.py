"""Stripe payment gateway adapter.

Gateway for US/Canada/international — supports cards, bank transfers.
Docs: https://stripe.com/docs/api
"""

from __future__ import annotations

import logging

import stripe

from app.services.payment.base import OrderResult, PaymentGateway, RefundResult, VerifyResult

logger = logging.getLogger(__name__)


class StripeGateway(PaymentGateway):
    def __init__(self, api_key: str, webhook_secret: str | None = None):
        self._api_key = api_key
        self._webhook_secret = webhook_secret or ""
        stripe.api_key = api_key

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
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": currency_code.lower(),
                        "unit_amount": amount_cents,
                        "product_data": {
                            "name": description or "IMS Subscription",
                        },
                    },
                    "quantity": 1,
                },
            ],
            metadata={
                "tenant_id": tenant_id,
                "subscription_id": subscription_id,
                **(metadata or {}),
            },
            # success_url and cancel_url would come from config in production
            success_url="https://platform.example.com/payments/success?session_id={CHECKOUT_SESSION_ID}",
            cancel_url="https://platform.example.com/payments/cancel",
        )
        logger.info("Stripe session created: %s for %s %s", session.id, currency_code, amount_cents)
        return OrderResult(
            gateway_order_id=session.id,
            amount_cents=amount_cents,
            currency_code=currency_code,
            checkout_url=session.url,
            metadata={"stripe_session_id": session.id},
        )

    def verify_payment(
        self,
        *,
        gateway_order_id: str,
        gateway_payment_id: str,
        gateway_signature: str | None = None,
    ) -> VerifyResult:
        session = stripe.checkout.Session.retrieve(gateway_order_id)
        success = session.payment_status == "paid"
        pi_id = session.payment_intent or gateway_payment_id
        return VerifyResult(
            success=success,
            gateway_payment_id=str(pi_id),
            method="card",
            metadata={"stripe_session": {"id": session.id, "status": session.payment_status}},
        )

    def process_refund(
        self,
        *,
        gateway_payment_id: str,
        amount_cents: int,
    ) -> RefundResult:
        refund = stripe.Refund.create(
            payment_intent=gateway_payment_id,
            amount=amount_cents,
        )
        return RefundResult(
            success=refund.status in ("succeeded", "pending"),
            refund_id=refund.id,
            amount_cents=refund.amount or amount_cents,
            metadata={"stripe_refund_id": refund.id},
        )

    def verify_webhook_signature(self, *, payload: bytes, headers: dict[str, str]) -> bool:
        sig = headers.get("stripe-signature", "")
        try:
            stripe.Webhook.construct_event(payload, sig, self._webhook_secret)
            return True
        except (stripe.error.SignatureVerificationError, ValueError):
            return False
