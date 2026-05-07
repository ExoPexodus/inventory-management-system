"""Admin endpoints for configuring transactional email via Resend.

Merchants supply their own Resend API key and verified sender domain.
Once configured, all order confirmations are sent from their own domain
via their own Resend account — IMS never shares email infrastructure.
"""
from __future__ import annotations

from typing import Annotated
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


class EmailConfigureIn(BaseModel):
    resend_api_key: str = Field(min_length=1)
    from_email: str = Field(min_length=3, max_length=255)
    from_name: str = Field(default="", max_length=255)


class EmailConfigureOut(BaseModel):
    configured: bool
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


@router.get("/config", response_model=EmailConfigureOut)
def get_config(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> EmailConfigureOut:
    tenant_id = _require_tenant(ctx)
    config = _get_config(db, tenant_id)
    if config is None:
        return EmailConfigureOut(configured=False, from_email=None, from_name=None)
    api_key = decrypt_secret(config.api_key_encrypted)
    return EmailConfigureOut(
        configured=bool(api_key and config.from_email),
        from_email=config.from_email,
        from_name=config.from_name,
    )


@router.post("/configure", response_model=EmailConfigureOut)
def configure_email(
    body: EmailConfigureIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> EmailConfigureOut:
    tenant_id = _require_tenant(ctx)
    config = _get_config(db, tenant_id)
    if config is None:
        config = TenantEmailConfig(tenant_id=tenant_id, provider="resend", from_email=body.from_email)
        db.add(config)
    else:
        config.provider = "resend"
        config.from_email = body.from_email.strip()

    config.api_key_encrypted = encrypt_secret(body.resend_api_key.strip())
    config.from_name = body.from_name.strip() or None
    db.commit()

    return EmailConfigureOut(
        configured=True,
        from_email=config.from_email,
        from_name=config.from_name,
    )


@router.post("/test-send", response_model=TestSendOut)
def test_send(
    body: TestSendIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> TestSendOut:
    tenant_id = _require_tenant(ctx)
    config = _get_config(db, tenant_id)
    if config is None:
        raise HTTPException(status_code=400, detail="Email not configured for this tenant")

    api_key = decrypt_secret(config.api_key_encrypted)
    if not api_key or not config.from_email:
        raise HTTPException(status_code=400, detail="Email not configured for this tenant")

    sent = send_test_email(
        api_key=api_key,
        from_email=config.from_email,
        from_name=config.from_name or "",
        to_email=body.to_email,
    )
    return TestSendOut(
        sent=sent,
        message="Test email sent successfully" if sent else (
            "Failed to send — check your Resend API key and from_email domain"
        ),
    )
