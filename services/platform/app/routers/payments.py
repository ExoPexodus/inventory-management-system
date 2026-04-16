"""Payment management endpoints — create orders, record manual payments, handle webhooks."""

from __future__ import annotations

import logging
import uuid as _uuid
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import OperatorDep
from app.db.session import get_db
from app.models.tables import Payment, PlatformTenant, Subscription
from app.services.audit_service import write_audit
from app.services.payment.factory import get_gateway, get_gateway_for_tenant
from app.services.payment.manual_gw import ManualGateway

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/platform", tags=["Platform Payments"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PaymentOut(BaseModel):
    id: UUID
    tenant_id: UUID
    subscription_id: UUID
    amount_cents: int
    currency_code: str
    gateway: str
    gateway_payment_id: str | None
    gateway_order_id: str | None
    status: str
    method: str | None
    paid_at: datetime | None
    created_at: datetime


class CreateOrderRequest(BaseModel):
    description: str = "Subscription payment"


class CreateOrderResponse(BaseModel):
    payment_id: UUID
    gateway: str
    gateway_order_id: str
    amount_cents: int
    currency_code: str
    checkout_url: str | None


class VerifyPaymentRequest(BaseModel):
    gateway_payment_id: str
    gateway_signature: str | None = None


class ManualPaymentRequest(BaseModel):
    amount_cents: int
    currency_code: str = "INR"
    method: str = "bank_transfer"
    notes: str | None = None


# ---------------------------------------------------------------------------
# List payments
# ---------------------------------------------------------------------------


@router.get("/payments", response_model=list[PaymentOut])
def list_payments(
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
    pay_status: str | None = Query(default=None, alias="status"),
    tenant_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[PaymentOut]:
    stmt = select(Payment).order_by(Payment.created_at.desc())
    if pay_status:
        stmt = stmt.where(Payment.status == pay_status)
    if tenant_id:
        stmt = stmt.where(Payment.tenant_id == tenant_id)
    stmt = stmt.limit(limit)
    rows = db.execute(stmt).scalars().all()
    return [_to_out(p) for p in rows]


@router.get("/tenants/{tenant_id}/payments", response_model=list[PaymentOut])
def list_tenant_payments(
    tenant_id: UUID,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=200),
) -> list[PaymentOut]:
    rows = db.execute(
        select(Payment)
        .where(Payment.tenant_id == tenant_id)
        .order_by(Payment.created_at.desc())
        .limit(limit)
    ).scalars().all()
    return [_to_out(p) for p in rows]


# ---------------------------------------------------------------------------
# Create payment order (initiates checkout)
# ---------------------------------------------------------------------------


@router.post("/tenants/{tenant_id}/payments/create-order", response_model=CreateOrderResponse)
def create_payment_order(
    tenant_id: UUID,
    body: CreateOrderRequest,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> CreateOrderResponse:
    tenant = db.get(PlatformTenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    sub = db.execute(
        select(Subscription)
        .where(Subscription.tenant_id == tenant_id)
        .order_by(Subscription.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No subscription for tenant")

    # Calculate amount from plan
    from app.models.tables import Addon, Plan, SubscriptionAddon
    plan = db.get(Plan, sub.plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Plan not found")

    # Base + addons
    amount = plan.base_price_cents
    if sub.billing_cycle == "yearly":
        amount = int(amount * 12 * (1 - plan.yearly_discount_pct / 100))

    addon_rows = db.execute(
        select(SubscriptionAddon, Addon)
        .join(Addon, Addon.id == SubscriptionAddon.addon_id)
        .where(
            SubscriptionAddon.subscription_id == sub.id,
            SubscriptionAddon.removed_at.is_(None),
        )
    ).all()
    for sa, addon in addon_rows:
        addon_price = addon.price_cents
        if sub.billing_cycle == "yearly":
            addon_price = int(addon_price * 12 * (1 - plan.yearly_discount_pct / 100))
        amount += addon_price

    gateway, gateway_name = get_gateway_for_tenant(db, tenant.region)

    order_result = gateway.create_order(
        amount_cents=amount,
        currency_code=plan.currency_code,
        tenant_id=str(tenant_id),
        subscription_id=str(sub.id),
        description=body.description,
    )

    # Record payment row as pending
    payment = Payment(
        id=_uuid.uuid4(),
        tenant_id=tenant_id,
        subscription_id=sub.id,
        amount_cents=order_result.amount_cents,
        currency_code=order_result.currency_code,
        gateway=gateway_name,
        gateway_order_id=order_result.gateway_order_id,
        status="pending",
    )
    db.add(payment)
    write_audit(db, operator_id=ctx.operator_id, action="create_payment_order", resource_type="payment", resource_id=str(payment.id))
    db.commit()
    db.refresh(payment)

    return CreateOrderResponse(
        payment_id=payment.id,
        gateway=gateway_name,
        gateway_order_id=order_result.gateway_order_id,
        amount_cents=order_result.amount_cents,
        currency_code=order_result.currency_code,
        checkout_url=order_result.checkout_url,
    )


# ---------------------------------------------------------------------------
# Verify payment (after client-side completion)
# ---------------------------------------------------------------------------


@router.post("/tenants/{tenant_id}/payments/{payment_id}/verify", response_model=PaymentOut)
def verify_payment(
    tenant_id: UUID,
    payment_id: UUID,
    body: VerifyPaymentRequest,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> PaymentOut:
    payment = db.get(Payment, payment_id)
    if payment is None or payment.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    if payment.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Payment is already {payment.status}")

    gateway = get_gateway(db, gateway_name=payment.gateway, region="in")
    result = gateway.verify_payment(
        gateway_order_id=payment.gateway_order_id or "",
        gateway_payment_id=body.gateway_payment_id,
        gateway_signature=body.gateway_signature,
    )

    if result.success:
        payment.status = "succeeded"
        payment.gateway_payment_id = result.gateway_payment_id
        payment.method = result.method
        payment.paid_at = datetime.now(UTC)
        _activate_subscription_on_payment(db, payment)
    else:
        payment.status = "failed"

    write_audit(db, operator_id=ctx.operator_id, action="verify_payment", resource_type="payment", resource_id=str(payment_id), details={"success": result.success})
    db.commit()
    db.refresh(payment)
    return _to_out(payment)


# ---------------------------------------------------------------------------
# Record manual/offline payment
# ---------------------------------------------------------------------------


@router.post("/tenants/{tenant_id}/payments/manual", response_model=PaymentOut)
def record_manual_payment(
    tenant_id: UUID,
    body: ManualPaymentRequest,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> PaymentOut:
    tenant = db.get(PlatformTenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    sub = db.execute(
        select(Subscription)
        .where(Subscription.tenant_id == tenant_id)
        .order_by(Subscription.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No subscription for tenant")

    manual = ManualGateway()
    order = manual.create_order(
        amount_cents=body.amount_cents,
        currency_code=body.currency_code,
        tenant_id=str(tenant_id),
        subscription_id=str(sub.id),
    )

    payment = Payment(
        id=_uuid.uuid4(),
        tenant_id=tenant_id,
        subscription_id=sub.id,
        amount_cents=body.amount_cents,
        currency_code=body.currency_code,
        gateway="manual",
        gateway_order_id=order.gateway_order_id,
        gateway_payment_id=order.gateway_order_id,
        status="succeeded",
        method=body.method,
        metadata_json={"notes": body.notes} if body.notes else None,
        paid_at=datetime.now(UTC),
    )
    db.add(payment)
    _activate_subscription_on_payment(db, payment)

    write_audit(db, operator_id=ctx.operator_id, action="record_manual_payment", resource_type="payment", resource_id=str(payment.id), details={"amount": body.amount_cents, "method": body.method})
    db.commit()
    db.refresh(payment)
    return _to_out(payment)


# ---------------------------------------------------------------------------
# Webhook endpoints (called by payment gateways)
# ---------------------------------------------------------------------------


@router.post("/payments/webhooks/razorpay", status_code=200)
async def razorpay_webhook(request: Request, db: Annotated[Session, Depends(get_db)]) -> dict:
    return await _handle_webhook(request, db, "razorpay")


@router.post("/payments/webhooks/stripe", status_code=200)
async def stripe_webhook(request: Request, db: Annotated[Session, Depends(get_db)]) -> dict:
    return await _handle_webhook(request, db, "stripe")


async def _handle_webhook(request: Request, db: Session, gateway_name: str) -> dict:
    payload = await request.body()
    headers = dict(request.headers)

    gateway = get_gateway(db, gateway_name=gateway_name)
    if not gateway.verify_webhook_signature(payload=payload, headers=headers):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")

    # Parse the event — each gateway has different payload structures
    # For now, log and acknowledge. Full parsing depends on gateway-specific event types.
    import json
    try:
        event = json.loads(payload)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")

    logger.info("Webhook received from %s: %s", gateway_name, event.get("event", event.get("type", "unknown")))

    # Razorpay: event "payment.captured" → find payment by order_id, mark succeeded
    # Stripe: event "checkout.session.completed" → find payment by session_id, mark succeeded
    # Implementation would extract IDs and call _process_webhook_payment(db, ...)

    return {"status": "received"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _activate_subscription_on_payment(db: Session, payment: Payment) -> None:
    """When a payment succeeds, activate/renew the subscription."""
    sub = db.get(Subscription, payment.subscription_id)
    if sub is None:
        return

    from app.services.subscription_service import activate_subscription, can_transition
    if can_transition(sub.status, "active"):
        activate_subscription(db, sub)


def _to_out(p: Payment) -> PaymentOut:
    return PaymentOut(
        id=p.id,
        tenant_id=p.tenant_id,
        subscription_id=p.subscription_id,
        amount_cents=p.amount_cents,
        currency_code=p.currency_code,
        gateway=p.gateway,
        gateway_payment_id=p.gateway_payment_id,
        gateway_order_id=p.gateway_order_id,
        status=p.status,
        method=p.method,
        paid_at=p.paid_at,
        created_at=p.created_at,
    )
