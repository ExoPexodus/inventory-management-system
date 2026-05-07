"""Admin endpoints for configuring transactional email.

Supports SMTP (e.g. Hostinger, Gmail, any mail host) and Resend.
Configure once; all order confirmations send automatically from there.
"""
from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import TenantEmailConfig
from app.services.email_service import decrypt_secret, encrypt_secret, send_test_email

router = APIRouter(
    prefix="/v1/admin/email",
    tags=["Email Configuration"],
    dependencies=[require_permission("email:manage")],
)


class SmtpConfigureIn(BaseModel):
    provider: Literal["smtp"]
    smtp_host: str = Field(min_length=1, max_length=255)
    smtp_port: int = Field(ge=1, le=65535)
    smtp_username: str = Field(min_length=1, max_length=255)
    smtp_password: str = Field(min_length=1)
    from_email: str = Field(min_length=3, max_length=255)
    from_name: str = Field(default="", max_length=255)


class ResendConfigureIn(BaseModel):
    provider: Literal["resend"]
    resend_api_key: str = Field(min_length=1)
    from_email: str = Field(min_length=3, max_length=255)
    from_name: str = Field(default="", max_length=255)


class EmailConfigureOut(BaseModel):
    configured: bool
    provider: str | None
    from_email: str | None
    from_name: str | None


class TestSendIn(BaseModel):
    to_email: str = Field(min_length=3, max_length=255)


class TestSendOut(BaseModel):
    sent: bool
    message: str


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Operator not assigned to a tenant")
    return ctx.tenant_id


def _get_config(db: Session, tenant_id: UUID) -> TenantEmailConfig | None:
    return db.execute(
        select(TenantEmailConfig).where(TenantEmailConfig.tenant_id == tenant_id)
    ).scalar_one_or_none()


def _is_configured(config: TenantEmailConfig) -> bool:
    if not config.from_email:
        return False
    provider = (config.provider or "").strip().lower()
    if provider == "smtp":
        return bool(config.smtp_host and config.smtp_port)
    if provider in ("resend", "sendgrid"):
        return bool(decrypt_secret(config.api_key_encrypted))
    return False


@router.get("/config", response_model=EmailConfigureOut)
def get_config(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> EmailConfigureOut:
    tenant_id = _require_tenant(ctx)
    config = _get_config(db, tenant_id)
    if config is None:
        return EmailConfigureOut(configured=False, provider=None, from_email=None, from_name=None)
    return EmailConfigureOut(
        configured=_is_configured(config),
        provider=config.provider,
        from_email=config.from_email,
        from_name=config.from_name,
    )


@router.post("/configure/smtp", response_model=EmailConfigureOut)
def configure_smtp(
    body: SmtpConfigureIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> EmailConfigureOut:
    """Configure Hostinger, Gmail, or any SMTP mail server."""
    tenant_id = _require_tenant(ctx)
    config = _get_config(db, tenant_id)
    if config is None:
        config = TenantEmailConfig(tenant_id=tenant_id, provider="smtp", from_email=body.from_email)
        db.add(config)

    config.provider = "smtp"
    config.smtp_host = body.smtp_host.strip()
    config.smtp_port = body.smtp_port
    config.smtp_username = body.smtp_username.strip()
    config.smtp_password_encrypted = encrypt_secret(body.smtp_password)
    config.from_email = body.from_email.strip()
    config.from_name = body.from_name.strip() or None
    # Clear Resend key if switching from Resend
    config.api_key_encrypted = None
    db.commit()

    return EmailConfigureOut(
        configured=True,
        provider="smtp",
        from_email=config.from_email,
        from_name=config.from_name,
    )


@router.post("/configure/resend", response_model=EmailConfigureOut)
def configure_resend(
    body: ResendConfigureIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> EmailConfigureOut:
    """Configure Resend as the email provider."""
    tenant_id = _require_tenant(ctx)
    config = _get_config(db, tenant_id)
    if config is None:
        config = TenantEmailConfig(tenant_id=tenant_id, provider="resend", from_email=body.from_email)
        db.add(config)

    config.provider = "resend"
    config.api_key_encrypted = encrypt_secret(body.resend_api_key.strip())
    config.from_email = body.from_email.strip()
    config.from_name = body.from_name.strip() or None
    # Clear SMTP fields if switching from SMTP
    config.smtp_host = None
    config.smtp_port = None
    config.smtp_username = None
    config.smtp_password_encrypted = None
    db.commit()

    return EmailConfigureOut(
        configured=True,
        provider="resend",
        from_email=config.from_email,
        from_name=config.from_name,
    )


# Keep the old /configure endpoint working (defaults to resend) for backwards compat
@router.post("/configure", response_model=EmailConfigureOut, include_in_schema=False)
def configure_email_legacy(
    body: ResendConfigureIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> EmailConfigureOut:
    return configure_resend(body, ctx, db)


@router.post("/test-send", response_model=TestSendOut)
def test_send(
    body: TestSendIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> TestSendOut:
    tenant_id = _require_tenant(ctx)
    config = _get_config(db, tenant_id)
    if config is None or not _is_configured(config):
        raise HTTPException(status_code=400, detail="Email not configured for this tenant")

    sent = send_test_email(config, to_email=body.to_email)
    return TestSendOut(
        sent=sent,
        message="Test email sent successfully" if sent else (
            "Failed to send — check your SMTP credentials or API key"
        ),
    )
