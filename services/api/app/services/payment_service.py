"""Payment service: Stripe and Razorpay."""
from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

import httpx

from app.services.email_service import decrypt_secret

logger = logging.getLogger(__name__)


class PaymentProviderError(Exception):
    pass


class PaymentNotConfiguredError(Exception):
    pass


def _get_provider(channel) -> str:
    p = channel.config.get("payment_provider", "none")
    if p == "none" or not p:
        raise PaymentNotConfiguredError(f"Channel {channel.id} has no payment provider configured")
    return p


def create_payment_intent(channel, amount_cents: int, currency: str,
                          description: str = "IMS Checkout") -> dict[str, Any]:
    provider = _get_provider(channel)
    if provider == "stripe":
        return _create_stripe_intent(channel, amount_cents, currency, description)
    elif provider == "razorpay":
        return _create_razorpay_order(channel, amount_cents, currency)
    raise PaymentNotConfiguredError(f"Unknown payment provider: {provider}")


def verify_payment(channel, payment_id: str) -> bool:
    provider = _get_provider(channel)
    if provider == "stripe":
        return _verify_stripe(channel, payment_id)
    return False


def verify_razorpay_signature(channel, razorpay_order_id: str,
                               razorpay_payment_id: str, razorpay_signature: str) -> bool:
    key_secret = decrypt_secret(channel.config.get("razorpay_key_secret", "")) or ""
    expected = hmac.new(
        key_secret.encode(),
        f"{razorpay_order_id}|{razorpay_payment_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, razorpay_signature)


def _create_stripe_intent(channel, amount_cents: int, currency: str, description: str) -> dict:
    import stripe
    stripe.api_key = decrypt_secret(channel.config.get("stripe_secret_key", "")) or ""
    intent = stripe.PaymentIntent.create(
        amount=amount_cents, currency=currency.lower(),
        description=description,
        automatic_payment_methods={"enabled": True},
    )
    return {"provider": "stripe", "payment_intent_id": intent.id, "client_secret": intent.client_secret}


def _verify_stripe(channel, payment_intent_id: str) -> bool:
    import stripe
    stripe.api_key = decrypt_secret(channel.config.get("stripe_secret_key", "")) or ""
    try:
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        return intent.status == "succeeded"
    except Exception:
        logger.warning("Failed to verify Stripe payment %s", payment_intent_id, exc_info=True)
        return False


def _create_razorpay_order(channel, amount_cents: int, currency: str) -> dict:
    key_id = channel.config.get("razorpay_key_id", "")
    key_secret = decrypt_secret(channel.config.get("razorpay_key_secret", "")) or ""
    resp = httpx.post(
        "https://api.razorpay.com/v1/orders",
        auth=(key_id, key_secret),
        json={"amount": amount_cents, "currency": currency.upper(), "receipt": "ims_checkout"},
        timeout=15.0,
    )
    if resp.status_code != 200:
        raise PaymentProviderError(f"Razorpay order creation failed: HTTP {resp.status_code}")
    data = resp.json()
    return {"provider": "razorpay", "order_id": data["id"], "key_id": key_id,
            "amount": data["amount"], "currency": data["currency"]}
