"""License sync service — pulls license state from the platform service and caches locally.

The main API calls the platform service periodically (via RQ task) and on-demand
when the cache is stale. If the platform service is unreachable, the cached data
is used as a fallback.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from datetime import UTC, datetime
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Tenant, TenantLicenseCache

logger = logging.getLogger(__name__)

STALE_THRESHOLD_SECONDS = 600  # 10 minutes — after this, cache is considered stale


def sync_tenant_license(db: Session, tenant_id: UUID) -> TenantLicenseCache | None:
    """Fetch license state from platform and upsert local cache. Returns None on failure."""
    if not settings.platform_api_url:
        return None

    url = f"{settings.platform_api_url}/v1/platform/license/{tenant_id}"
    ts = str(int(time.time()))
    message = f"{ts}|{tenant_id}"
    sig = hmac.new(settings.platform_api_secret.encode(), message.encode(), hashlib.sha256).hexdigest()

    try:
        resp = httpx.get(
            url,
            headers={
                "X-Platform-Auth": sig,
                "X-Platform-Timestamp": ts,
            },
            timeout=10.0,
        )
        if resp.status_code != 200:
            logger.warning("Platform license fetch failed for %s: HTTP %s", tenant_id, resp.status_code)
            return None

        data = resp.json()
    except Exception:
        logger.warning("Platform service unreachable for tenant %s", tenant_id, exc_info=True)
        return None

    return _upsert_cache(db, tenant_id, data)


def _upsert_cache(db: Session, tenant_id: UUID, data: dict) -> TenantLicenseCache:
    """Insert or update the local license cache for a tenant."""
    now = datetime.now(UTC)
    cache = db.execute(
        select(TenantLicenseCache).where(TenantLicenseCache.tenant_id == tenant_id)
    ).scalar_one_or_none()

    if cache is None:
        cache = TenantLicenseCache(tenant_id=tenant_id, last_synced_at=now)
        db.add(cache)

    cache.subscription_status = data.get("subscription_status", "unknown")
    cache.plan_codename = data.get("plan_codename", "none")
    cache.billing_cycle = data.get("billing_cycle")
    cache.active_addons = data.get("active_addons", [])
    cache.max_shops = data.get("max_shops", 1)
    cache.max_employees = data.get("max_employees", 5)
    cache.storage_limit_mb = data.get("storage_limit_mb", 500)
    cache.grace_period_days = data.get("grace_period_days", 7)
    cache.is_in_grace_period = data.get("is_in_grace_period", False)
    cache.last_synced_at = now
    cache.raw_payload = data

    # Parse optional datetime strings
    trial_ends = data.get("trial_ends_at")
    cache.trial_ends_at = datetime.fromisoformat(trial_ends) if trial_ends else None
    period_end = data.get("current_period_end")
    cache.current_period_end = datetime.fromisoformat(period_end) if period_end else None

    db.flush()
    return cache


def get_cached_license(db: Session, tenant_id: UUID) -> TenantLicenseCache | None:
    """Read local license cache. Returns None if no cache entry exists."""
    return db.execute(
        select(TenantLicenseCache).where(TenantLicenseCache.tenant_id == tenant_id)
    ).scalar_one_or_none()


def is_cache_stale(cache: TenantLicenseCache | None) -> bool:
    """Check if the cache is missing or older than STALE_THRESHOLD_SECONDS."""
    if cache is None:
        return True
    age = (datetime.now(UTC) - cache.last_synced_at.replace(tzinfo=UTC)).total_seconds()
    return age > STALE_THRESHOLD_SECONDS


def sync_all_tenant_licenses(db: Session) -> int:
    """Sync license state for all tenants. Returns count of successful syncs."""
    tenants = db.execute(select(Tenant)).scalars().all()
    success = 0
    for tenant in tenants:
        result = sync_tenant_license(db, tenant.id)
        if result is not None:
            success += 1
    db.commit()
    return success
