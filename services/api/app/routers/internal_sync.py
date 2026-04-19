"""Internal sync endpoints for receiving pushes from the platform service."""
from __future__ import annotations

import hmac
import hashlib
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.models import Tenant

router = APIRouter(prefix="/v1/internal", tags=["Internal Sync"])

HMAC_SKEW_SECONDS = 300
CLOCK_SKEW_TOLERANCE_SECONDS = 2


class PlatformConfigPayload(BaseModel):
    tenant_id: UUID
    default_currency_code: str
    currency_exponent: int
    currency_symbol_override: str | None
    synced_at: str


def verify_push_hmac(signature: str | None, timestamp: str | None, tenant_id: str) -> None:
    if not signature or not timestamp:
        raise HTTPException(status_code=401, detail="Missing HMAC headers")
    try:
        ts_dt = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid timestamp format")
    if abs((datetime.now(UTC) - ts_dt).total_seconds()) > HMAC_SKEW_SECONDS:
        raise HTTPException(status_code=401, detail="Stale timestamp")

    expected = hmac.new(
        settings.platform_api_secret.encode("utf-8"),
        f"{timestamp}|{tenant_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")


def apply_platform_config(db: Session, payload: PlatformConfigPayload) -> dict:
    """Apply a config push if synced_at is newer than the stored value."""
    tenant = db.get(Tenant, payload.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    payload_ts = datetime.strptime(payload.synced_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    if tenant.currency_synced_at is not None:
        delta = (payload_ts - tenant.currency_synced_at).total_seconds()
        if delta <= CLOCK_SKEW_TOLERANCE_SECONDS:
            return {"applied": False, "reason": "payload not newer"}

    tenant.default_currency_code = payload.default_currency_code
    tenant.currency_exponent = payload.currency_exponent
    tenant.currency_symbol_override = payload.currency_symbol_override
    tenant.currency_synced_at = payload_ts
    db.commit()
    return {"applied": True}


@router.post("/platform-config")
def receive_platform_config(
    payload: PlatformConfigPayload,
    db: Annotated[Session, Depends(get_db)],
    x_platform_auth: Annotated[str | None, Header()] = None,
    x_platform_timestamp: Annotated[str | None, Header()] = None,
) -> dict:
    verify_push_hmac(x_platform_auth, x_platform_timestamp, str(payload.tenant_id))
    return apply_platform_config(db, payload)
