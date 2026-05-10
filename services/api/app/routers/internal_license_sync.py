"""Internal endpoint: platform → IMS license sync trigger.

Accepts a HMAC-signed POST from the platform service to immediately sync
a single tenant's license cache without waiting for the next polling cycle.

Authentication mirrors the pattern used by `routers/license.py` in the
platform service — a shared secret signed as `SHA256(timestamp|tenant_id)`.
The secret is `settings.platform_api_secret` on the IMS side.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.billing.entitlements import invalidate_cache
from app.config import settings
from app.db.session import get_db
from app.services.license_service import sync_tenant_license

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/internal", tags=["Internal Platform Sync"])

MAX_TIMESTAMP_DRIFT_SECONDS = 300  # 5 minutes


class SyncTriggerBody(BaseModel):
    tenant_id: UUID


def _verify_platform_hmac(request: Request, tenant_id: UUID) -> None:
    auth = request.headers.get("X-Platform-Auth")
    ts_h = request.headers.get("X-Platform-Timestamp")
    if not auth or not ts_h:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing auth headers")
    try:
        ts = int(ts_h)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid timestamp")
    if abs(time.time() - ts) > MAX_TIMESTAMP_DRIFT_SECONDS:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Timestamp too old")

    secret = settings.platform_api_secret
    msg = f"{ts}|{tenant_id}"
    expected = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(auth, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")


@router.post("/license-sync-trigger", status_code=202)
def trigger_sync(
    body: SyncTriggerBody,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """Immediately sync the license cache for the given tenant.

    Called by the platform service after a plan-features update when
    `apply_to_existing=True` is requested.
    """
    _verify_platform_hmac(request, body.tenant_id)
    result = sync_tenant_license(db, body.tenant_id)
    if result is not None:
        db.commit()
        # Invalidate the Redis entitlement cache so fresh plan_features take effect
        invalidate_cache(body.tenant_id)
    return {"synced": result is not None}
