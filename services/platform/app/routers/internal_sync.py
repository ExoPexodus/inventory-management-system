"""Internal sync endpoints for api→platform pull (HMAC-authenticated)."""
from __future__ import annotations

import hmac
import hashlib
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.models import PlatformTenant

router = APIRouter(prefix="/v1/internal", tags=["Internal Sync"])

HMAC_SKEW_SECONDS = 300  # 5 minutes allowed drift


def _verify_hmac(request: Request, slug: str) -> None:
    signature = request.headers.get("X-Platform-Auth")
    timestamp = request.headers.get("X-Platform-Timestamp")
    if not signature or not timestamp:
        raise HTTPException(status_code=401, detail="Missing HMAC headers")

    try:
        ts_dt = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid timestamp format")

    if abs((datetime.now(UTC) - ts_dt).total_seconds()) > HMAC_SKEW_SECONDS:
        raise HTTPException(status_code=401, detail="Stale timestamp")

    expected = hmac.new(
        settings.jwt_secret.encode("utf-8"),
        f"{timestamp}|{slug}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")


class TenantConfigOut(BaseModel):
    default_currency_code: str
    currency_exponent: int
    currency_symbol_override: str | None
    synced_at: str


@router.get("/tenants/{slug}/config", response_model=TenantConfigOut)
def get_tenant_config_internal(
    slug: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> TenantConfigOut:
    _verify_hmac(request, slug)

    tenant = db.execute(
        select(PlatformTenant).where(PlatformTenant.slug == slug)
    ).scalar_one_or_none()
    if tenant is None:
        # Return 401 not 404 to avoid leaking tenant existence
        raise HTTPException(status_code=401, detail="Invalid credentials")

    synced_at = tenant.updated_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    return TenantConfigOut(
        default_currency_code=tenant.default_currency_code,
        currency_exponent=tenant.currency_exponent,
        currency_symbol_override=tenant.currency_symbol_override,
        synced_at=synced_at,
    )
