"""Payment provider abstraction for executing refunds from an RMA.

Supports: stripe, razorpay, cash (manual), unknown/missing.
Returns a dict: {provider_ref: str|None, status: "completed"|"pending"|"failed"|"manual_cash"|"manual"}
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Channel, OrderPayment, PaymentAllocation
from app.services.email_service import decrypt_secret

logger = logging.getLogger(__name__)


def execute_provider_refund(
    db: Session,
    *,
    order=None,  # Order | None
    transaction=None,  # Transaction | None
    amount_cents: int,
) -> dict[str, Any]:
    """Attempt to issue a refund via the payment provider.

    Returns:
        {"provider_ref": str|None, "status": "completed"|"pending"|"failed"|"manual_cash"|"manual"}
    """
    if order is not None:
        return _refund_for_order(db, order=order, amount_cents=amount_cents)
    if transaction is not None:
        return _refund_for_transaction(db, transaction=transaction, amount_cents=amount_cents)
    return {"provider_ref": None, "status": "manual"}


# ---------------------------------------------------------------------------
# Order-based refund (e-commerce)
# ---------------------------------------------------------------------------

def _refund_for_order(db: Session, *, order, amount_cents: int) -> dict[str, Any]:
    payments = db.execute(
        select(OrderPayment).where(OrderPayment.order_id == order.id)
    ).scalars().all()

    if not payments:
        return {"provider_ref": None, "status": "manual"}

    # Use the first paid payment record
    payment = next((p for p in payments if p.status == "paid"), payments[0])
    provider = (payment.provider or "").lower()

    if provider == "stripe":
        return _stripe_refund(db, payment=payment, amount_cents=amount_cents, channel_id=order.channel_id)
    if provider == "razorpay":
        return _razorpay_refund(db, payment=payment, amount_cents=amount_cents, channel_id=order.channel_id)
    if provider in ("cash", "manual", ""):
        return {"provider_ref": None, "status": "manual_cash"}

    # Unknown provider — treat as manual
    return {"provider_ref": None, "status": "manual"}


# ---------------------------------------------------------------------------
# Transaction-based refund (POS)
# ---------------------------------------------------------------------------

def _refund_for_transaction(db: Session, *, transaction, amount_cents: int) -> dict[str, Any]:
    allocations = db.execute(
        select(PaymentAllocation).where(PaymentAllocation.transaction_id == transaction.id)
    ).scalars().all()

    if not allocations:
        return {"provider_ref": None, "status": "manual_cash"}

    # Find primary allocation
    alloc = allocations[0]
    tender = (alloc.tender_type or "").lower()
    gateway = (alloc.gateway_provider or "").lower()

    if tender == "cash":
        return {"provider_ref": None, "status": "manual_cash"}

    # Card / online payments from POS — channel may be available via source_channel_id
    channel_id = getattr(transaction, "source_channel_id", None)

    if gateway == "stripe" or tender == "card":
        if alloc.external_ref and channel_id:
            return _stripe_refund_by_ref(
                db, payment_intent_id=alloc.external_ref,
                amount_cents=amount_cents, channel_id=channel_id,
            )
    if gateway == "razorpay":
        if alloc.external_ref and channel_id:
            return _razorpay_refund_by_ref(
                db, payment_id=alloc.external_ref,
                amount_cents=amount_cents, channel_id=channel_id,
            )

    # Fallback
    return {"provider_ref": None, "status": "manual_cash"}


# ---------------------------------------------------------------------------
# Stripe helpers
# ---------------------------------------------------------------------------

def _get_channel_config(db: Session, channel_id) -> dict:
    channel = db.get(Channel, channel_id)
    return (channel.config or {}) if channel else {}


def _stripe_refund(db: Session, *, payment, amount_cents: int, channel_id) -> dict[str, Any]:
    payment_intent_id = payment.provider_ref
    if not payment_intent_id:
        return {"provider_ref": None, "status": "manual"}
    return _stripe_refund_by_ref(
        db, payment_intent_id=payment_intent_id,
        amount_cents=amount_cents, channel_id=channel_id,
    )


def _stripe_refund_by_ref(db: Session, *, payment_intent_id: str, amount_cents: int, channel_id) -> dict[str, Any]:
    try:
        import stripe  # type: ignore[import]
    except ImportError:
        logger.warning("stripe package not installed; falling back to manual")
        return {"provider_ref": None, "status": "manual"}

    config = _get_channel_config(db, channel_id)
    raw_key = config.get("stripe_secret_key", "")
    secret_key = decrypt_secret(raw_key) if raw_key else None
    if not secret_key:
        logger.warning("No Stripe secret key found for channel %s", channel_id)
        return {"provider_ref": None, "status": "manual"}

    try:
        refund = stripe.Refund.create(
            payment_intent=payment_intent_id,
            amount=amount_cents,
            api_key=secret_key,
        )
        return {"provider_ref": refund.get("id"), "status": "completed"}
    except stripe.error.StripeError as exc:  # type: ignore[attr-defined]
        logger.warning("Stripe refund failed: %s", exc)
        return {"provider_ref": None, "status": "failed", "error": str(exc)}
    except Exception as exc:
        logger.warning("Stripe refund unexpected error: %s", exc)
        return {"provider_ref": None, "status": "failed", "error": str(exc)}


# ---------------------------------------------------------------------------
# Razorpay helpers
# ---------------------------------------------------------------------------

def _razorpay_refund(db: Session, *, payment, amount_cents: int, channel_id) -> dict[str, Any]:
    payment_id = payment.provider_ref
    if not payment_id:
        return {"provider_ref": None, "status": "manual"}
    return _razorpay_refund_by_ref(
        db, payment_id=payment_id, amount_cents=amount_cents, channel_id=channel_id,
    )


def _razorpay_refund_by_ref(db: Session, *, payment_id: str, amount_cents: int, channel_id) -> dict[str, Any]:
    try:
        import razorpay  # type: ignore[import]
    except ImportError:
        logger.warning("razorpay package not installed; falling back to manual")
        return {"provider_ref": None, "status": "manual"}

    config = _get_channel_config(db, channel_id)
    key_id = config.get("razorpay_key_id", "")
    raw_secret = config.get("razorpay_key_secret", "")
    key_secret = decrypt_secret(raw_secret) if raw_secret else None

    if not key_id or not key_secret:
        logger.warning("No Razorpay credentials for channel %s", channel_id)
        return {"provider_ref": None, "status": "manual"}

    try:
        client = razorpay.Client(auth=(key_id, key_secret))
        refund = client.payment.refund(payment_id, {"amount": amount_cents})
        return {"provider_ref": refund.get("id"), "status": "completed"}
    except Exception as exc:
        logger.warning("Razorpay refund failed: %s", exc)
        return {"provider_ref": None, "status": "failed", "error": str(exc)}
