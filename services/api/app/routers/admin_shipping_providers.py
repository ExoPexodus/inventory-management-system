"""Admin endpoints for configuring carrier shipping providers on channels."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Channel
from app.services.email_service import decrypt_secret, encrypt_secret
from app.worker.queue import redis_conn

router = APIRouter(
    prefix="/v1/admin/channels",
    tags=["Shipping Providers"],
    dependencies=[require_permission("shipping:manage")],
)


class ShiprocketSetupIn(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)
    pickup_location: str = Field(min_length=1, max_length=255)
    shiprocket_channel_id: str = Field(default="", max_length=64)


class ShippingConfigOut(BaseModel):
    channel_id: UUID
    configured: bool
    provider: str | None
    pickup_location: str | None
    email: str | None


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Operator not assigned to a tenant")
    return ctx.tenant_id


def _get_channel(db: Session, channel_id: UUID, tenant_id: UUID) -> Channel:
    ch = db.get(Channel, channel_id)
    if ch is None or ch.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Channel not found")
    return ch


@router.post("/{channel_id}/shipping/setup-shiprocket", response_model=ShippingConfigOut)
def setup_shiprocket(
    channel_id: UUID,
    body: ShiprocketSetupIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ShippingConfigOut:
    """Configure Shiprocket for a channel. Validates credentials before storing."""
    tenant_id = _require_tenant(ctx)
    channel = _get_channel(db, channel_id, tenant_id)

    import httpx
    try:
        resp = httpx.post(
            "https://apiv2.shiprocket.in/v1/external/auth/login",
            json={"email": body.email.strip(), "password": body.password},
            timeout=15.0,
        )
        resp.raise_for_status()
        token = resp.json().get("token", "")
        if not token:
            raise HTTPException(
                status_code=400,
                detail="Shiprocket did not return a token — check credentials",
            )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Shiprocket credential validation failed: HTTP {exc.response.status_code}",
        )
    except httpx.RequestError:
        raise HTTPException(status_code=502, detail="Could not reach Shiprocket API")

    # Cache the fresh token
    from app.services.shipping.shiprocket.client import _cache_key, TOKEN_TTL_SECONDS
    redis_conn().setex(_cache_key(channel_id), TOKEN_TTL_SECONDS, token)

    channel.config = {
        **channel.config,
        "shipping_provider": "shiprocket",
        "shiprocket_email": body.email.strip(),
        "shiprocket_password": encrypt_secret(body.password),
        "shiprocket_pickup_location": body.pickup_location.strip(),
        "shiprocket_channel_id": body.shiprocket_channel_id.strip(),
    }
    db.commit()

    return ShippingConfigOut(
        channel_id=channel.id,
        configured=True,
        provider="shiprocket",
        pickup_location=body.pickup_location.strip(),
        email=body.email.strip(),
    )


@router.get("/{channel_id}/shipping/config", response_model=ShippingConfigOut)
def get_shipping_config(
    channel_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ShippingConfigOut:
    tenant_id = _require_tenant(ctx)
    channel = _get_channel(db, channel_id, tenant_id)
    provider = channel.config.get("shipping_provider")
    return ShippingConfigOut(
        channel_id=channel.id,
        configured=bool(provider),
        provider=provider,
        pickup_location=channel.config.get("shiprocket_pickup_location"),
        email=channel.config.get("shiprocket_email"),
    )


@router.delete("/{channel_id}/shipping/config", status_code=status.HTTP_204_NO_CONTENT)
def delete_shipping_config(
    channel_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    channel = _get_channel(db, channel_id, tenant_id)
    channel.config = {
        k: v for k, v in channel.config.items()
        if not k.startswith("shiprocket_") and k != "shipping_provider"
    }
    db.commit()
    try:
        from app.services.shipping.shiprocket.client import _cache_key
        redis_conn().delete(_cache_key(channel_id))
    except Exception:
        pass
