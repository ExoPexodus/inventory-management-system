"""License query endpoint — called by the main API to fetch tenant license state.

Authentication: HMAC-SHA256 signed request using a shared secret.
The main API sends:
  X-Platform-Auth: <hex HMAC of "timestamp|tenant_id">
  X-Platform-Timestamp: <unix timestamp>

The platform verifies the signature is valid and within a 5-minute window.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.models.tables import PlatformTenant
from app.services.subscription_service import build_license_state

router = APIRouter(prefix="/v1/platform/license", tags=["Platform License"])

MAX_TIMESTAMP_DRIFT_SECONDS = 300  # 5 minutes


class LicenseResponse(BaseModel):
    subscription_status: str
    plan_codename: str
    billing_cycle: str
    active_addons: list[str]
    max_shops: int
    max_employees: int
    storage_limit_mb: int
    trial_ends_at: str | None
    current_period_end: str | None
    grace_period_days: int
    is_in_grace_period: bool
    download_token: str | None = None


def _verify_hmac(request: Request, tenant_id: UUID) -> None:
    """Verify the HMAC signature from the main API."""
    auth_header = request.headers.get("X-Platform-Auth")
    ts_header = request.headers.get("X-Platform-Timestamp")

    if not auth_header or not ts_header:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing auth headers")

    try:
        ts = int(ts_header)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid timestamp")

    if abs(time.time() - ts) > MAX_TIMESTAMP_DRIFT_SECONDS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Timestamp too old")

    # Find the tenant's shared secret
    # For now, use a global secret from config. Per-tenant secrets would require a DB lookup.
    secret = settings.jwt_secret  # reusing jwt_secret as the HMAC key for now

    message = f"{ts}|{tenant_id}"
    expected = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(auth_header, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")


@router.get("/{tenant_id}", response_model=LicenseResponse)
def get_license(
    tenant_id: UUID,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> LicenseResponse:
    _verify_hmac(request, tenant_id)

    # Verify tenant exists
    tenant = db.get(PlatformTenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    state = build_license_state(db, tenant_id)
    if state is None:
        # No subscription — return a minimal "no_subscription" response
        return LicenseResponse(
            subscription_status="no_subscription",
            plan_codename="none",
            billing_cycle="none",
            active_addons=[],
            max_shops=0,
            max_employees=0,
            storage_limit_mb=0,
            trial_ends_at=None,
            current_period_end=None,
            grace_period_days=0,
            is_in_grace_period=False,
        )

    db.commit()  # persist any status changes (e.g. past_due → expired)
    return LicenseResponse(**state)
