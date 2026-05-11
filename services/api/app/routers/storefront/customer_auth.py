"""Storefront customer authentication via email OTP."""
from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import create_customer_token
from app.db.session import get_db
from app.models import Customer, StorefrontOTP, TenantEmailConfig
from app.routers.storefront.auth import StorefrontChannelDep
from app.services.customer_resolver import resolve_or_create_customer
from app.services.otp_rate_limit import check_otp_rate_limit

router = APIRouter(prefix="/v1/storefront/auth", tags=["Storefront Customer Auth"])

OTP_EXPIRY_MINUTES = 10


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def _generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


class OTPRequestIn(BaseModel):
    email: str


class OTPRequestOut(BaseModel):
    sent: bool
    message: str


class OTPVerifyIn(BaseModel):
    email: str
    code: str


class OTPVerifyOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/otp/request", response_model=OTPRequestOut)
def request_otp(
    body: OTPRequestIn,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
) -> OTPRequestOut:
    check_otp_rate_limit(email=body.email, channel_id=channel.id)
    code = _generate_otp()
    expires_at = datetime.now(UTC) + timedelta(minutes=OTP_EXPIRY_MINUTES)

    otp = StorefrontOTP(
        tenant_id=channel.tenant_id,
        channel_id=channel.id,
        email=body.email.lower().strip(),
        code_hash=_hash_code(code),
        expires_at=expires_at,
    )
    db.add(otp)
    db.commit()

    # Send via existing email infrastructure
    from app.services.email_service import (
        _from_header,
        _resend_send,
        _send_via_smtp,
        decrypt_secret,
    )

    config = db.execute(
        select(TenantEmailConfig).where(TenantEmailConfig.tenant_id == channel.tenant_id)
    ).scalar_one_or_none()

    sent = False
    if config and config.from_email:
        subject = "Your login code"
        html = (
            f"<p>Your login code for <strong>{channel.name}</strong> is:</p>"
            f"<p style='font-size:2rem;font-weight:bold;letter-spacing:.2em'>{code}</p>"
            f"<p style='color:#6b7280;font-size:.85rem'>Expires in {OTP_EXPIRY_MINUTES} minutes.</p>"
        )
        text = f"Your login code is: {code}. Expires in {OTP_EXPIRY_MINUTES} minutes."
        provider = (config.provider or "").strip().lower()
        try:
            if provider == "resend":
                api_key = decrypt_secret(config.api_key_encrypted)
                if api_key:
                    sent = _resend_send(api_key=api_key, from_address=_from_header(config),
                                        to_email=body.email, subject=subject, html=html)
            elif provider == "smtp":
                _send_via_smtp(config, to_email=body.email, subject=subject,
                               text_body=text, html_body=html)
                sent = True
        except Exception:
            pass

    return OTPRequestOut(
        sent=sent,
        message="Login code sent to your email." if sent else
                "Code generated. Configure email in settings to enable delivery.",
    )


@router.post("/otp/verify", response_model=OTPVerifyOut)
def verify_otp(
    body: OTPVerifyIn,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
) -> OTPVerifyOut:
    email = body.email.lower().strip()
    now = datetime.now(UTC)

    otp = db.execute(
        select(StorefrontOTP)
        .where(
            StorefrontOTP.channel_id == channel.id,
            StorefrontOTP.email == email,
            StorefrontOTP.code_hash == _hash_code(body.code.strip()),
            StorefrontOTP.used_at.is_(None),
            StorefrontOTP.expires_at > now,
        )
        .with_for_update()
    ).scalar_one_or_none()

    if otp is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid or expired login code")

    otp.used_at = now
    db.flush()

    customer = resolve_or_create_customer(db, channel.tenant_id, channel.id, email=email)
    if customer is None:
        customer = Customer(
            tenant_id=channel.tenant_id, phone="unknown", email=email,
            created_via_channel_id=channel.id,
        )
        db.add(customer)
        db.flush()

    db.commit()

    token, expires_in = create_customer_token(
        customer_id=customer.id,
        tenant_id=channel.tenant_id,
        channel_id=channel.id,
        email=email,
    )
    return OTPVerifyOut(access_token=token, token_type="bearer", expires_in=expires_in)


# ---------------------------------------------------------------------------
# Magic-link auth (alternative to OTP)
# ---------------------------------------------------------------------------

MAGIC_LINK_EXPIRY_MINUTES = 15


class MagicLinkRequestIn(BaseModel):
    email: str
    redirect_url: str


class MagicLinkRequestOut(BaseModel):
    sent: bool
    message: str


class MagicLinkVerifyIn(BaseModel):
    token: str


@router.post("/magic-link/request", response_model=MagicLinkRequestOut)
def request_magic_link(
    body: MagicLinkRequestIn,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
) -> MagicLinkRequestOut:
    check_otp_rate_limit(email=body.email, channel_id=channel.id)
    from app.models import StorefrontMagicLink
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(minutes=MAGIC_LINK_EXPIRY_MINUTES)

    link_row = StorefrontMagicLink(
        tenant_id=channel.tenant_id,
        channel_id=channel.id,
        email=body.email.lower().strip(),
        token_hash=_hash_code(token),
        redirect_url=body.redirect_url,
        expires_at=expires_at,
    )
    db.add(link_row)
    db.commit()

    # Compose the magic link URL
    sep = "&" if "?" in body.redirect_url else "?"
    magic_url = f"{body.redirect_url}{sep}token={token}"

    from app.services.email_service import (
        _from_header,
        _resend_send,
        _send_via_smtp,
        decrypt_secret,
    )

    config = db.execute(
        select(TenantEmailConfig).where(
            TenantEmailConfig.tenant_id == channel.tenant_id,
            TenantEmailConfig.is_active.is_(True),
        )
    ).scalar_one_or_none()

    subject = "Sign in"
    text_body = (
        f"Click this link to sign in: {magic_url}\n\n"
        f"This link expires in {MAGIC_LINK_EXPIRY_MINUTES} minutes and can only be used once."
    )
    html_body = (
        f"<html><body>"
        f"<p>Click the button below to sign in:</p>"
        f'<p><a href="{magic_url}" style="display:inline-block;padding:12px 24px;background:#3b82f6;'
        f'color:#fff;border-radius:8px;text-decoration:none;font-weight:bold;">Sign in</a></p>'
        f"<p>Or copy and paste this URL: {magic_url}</p>"
        f"<p><small>This link expires in {MAGIC_LINK_EXPIRY_MINUTES} minutes and can only be used once.</small></p>"
        f"</body></html>"
    )

    sent = False
    if config is not None and config.from_email:
        provider = (config.provider or "").strip().lower()
        try:
            if provider == "resend":
                api_key = decrypt_secret(config.api_key_encrypted)
                if api_key:
                    sent = _resend_send(
                        api_key=api_key,
                        from_address=_from_header(config),
                        to_email=body.email.lower().strip(),
                        subject=subject,
                        html=html_body,
                    )
            elif provider == "smtp":
                _send_via_smtp(
                    config,
                    to_email=body.email.lower().strip(),
                    subject=subject,
                    text_body=text_body,
                    html_body=html_body,
                )
                sent = True
        except Exception:
            sent = False

    return MagicLinkRequestOut(
        sent=sent,
        message=(
            "If an account matches that email, a sign-in link has been sent."
            if sent
            else "Configure email in settings to enable delivery."
        ),
    )


@router.post("/magic-link/verify", response_model=OTPVerifyOut)
def verify_magic_link(
    body: MagicLinkVerifyIn,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
) -> OTPVerifyOut:
    from app.models import StorefrontMagicLink
    now = datetime.now(UTC)
    token_hash = _hash_code(body.token.strip())

    link_row = db.execute(
        select(StorefrontMagicLink)
        .where(
            StorefrontMagicLink.channel_id == channel.id,
            StorefrontMagicLink.token_hash == token_hash,
            StorefrontMagicLink.used_at.is_(None),
            StorefrontMagicLink.expires_at > now,
        )
        .with_for_update()
    ).scalar_one_or_none()

    if link_row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired magic link",
        )

    link_row.used_at = now
    db.flush()

    email = link_row.email
    customer = resolve_or_create_customer(db, channel.tenant_id, channel.id, email=email)
    if customer is None:
        customer = Customer(
            tenant_id=channel.tenant_id, phone="unknown", email=email,
            created_via_channel_id=channel.id,
        )
        db.add(customer)
        db.flush()

    db.commit()

    token, expires_in = create_customer_token(
        customer_id=customer.id,
        tenant_id=channel.tenant_id,
        channel_id=channel.id,
        email=email,
    )
    return OTPVerifyOut(access_token=token, token_type="bearer", expires_in=expires_in)
