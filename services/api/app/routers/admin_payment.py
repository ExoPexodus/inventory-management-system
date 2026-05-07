"""Admin endpoints for configuring payment providers on a channel."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Channel
from app.services.email_service import encrypt_secret

router = APIRouter(
    prefix="/v1/admin/channels",
    tags=["Payment Setup"],
    dependencies=[require_permission("channels:manage")],
)


class StripeSetupIn(BaseModel):
    stripe_secret_key: str
    stripe_publishable_key: str
    checkout_success_url: str
    checkout_cancel_url: str = ""


class RazorpaySetupIn(BaseModel):
    razorpay_key_id: str
    razorpay_key_secret: str
    checkout_success_url: str
    checkout_cancel_url: str = ""


class PaymentSetupOut(BaseModel):
    channel_id: UUID
    payment_provider: str
    configured: bool


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Operator not assigned to a tenant")
    return ctx.tenant_id


def _get_channel_or_404(db: Session, channel_id: UUID, tenant_id: UUID) -> Channel:
    ch = db.get(Channel, channel_id)
    if ch is None or ch.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Channel not found")
    return ch


@router.post("/{channel_id}/payment/setup-stripe", response_model=PaymentSetupOut)
def setup_stripe(
    channel_id: UUID, body: StripeSetupIn, ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> PaymentSetupOut:
    tenant_id = _require_tenant(ctx)
    channel = _get_channel_or_404(db, channel_id, tenant_id)
    channel.config = {
        **channel.config,
        "payment_provider": "stripe",
        "stripe_secret_key": encrypt_secret(body.stripe_secret_key.strip()),
        "stripe_publishable_key": body.stripe_publishable_key.strip(),
        "checkout_success_url": body.checkout_success_url.strip(),
        "checkout_cancel_url": body.checkout_cancel_url.strip(),
    }
    db.commit()
    return PaymentSetupOut(channel_id=channel.id, payment_provider="stripe", configured=True)


@router.post("/{channel_id}/payment/setup-razorpay", response_model=PaymentSetupOut)
def setup_razorpay(
    channel_id: UUID, body: RazorpaySetupIn, ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> PaymentSetupOut:
    tenant_id = _require_tenant(ctx)
    channel = _get_channel_or_404(db, channel_id, tenant_id)
    channel.config = {
        **channel.config,
        "payment_provider": "razorpay",
        "razorpay_key_id": body.razorpay_key_id.strip(),
        "razorpay_key_secret": encrypt_secret(body.razorpay_key_secret.strip()),
        "checkout_success_url": body.checkout_success_url.strip(),
        "checkout_cancel_url": body.checkout_cancel_url.strip(),
    }
    db.commit()
    return PaymentSetupOut(channel_id=channel.id, payment_provider="razorpay", configured=True)


@router.get("/{channel_id}/payment/config", response_model=PaymentSetupOut)
def get_payment_config(
    channel_id: UUID, ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> PaymentSetupOut:
    tenant_id = _require_tenant(ctx)
    channel = _get_channel_or_404(db, channel_id, tenant_id)
    provider = channel.config.get("payment_provider", "none")
    return PaymentSetupOut(channel_id=channel.id, payment_provider=provider, configured=provider != "none")
