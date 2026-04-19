"""Poll platform service for authoritative tenant config."""
from __future__ import annotations

import hmac
import hashlib
import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Tenant
from app.routers.internal_sync import PlatformConfigPayload, apply_platform_config

logger = logging.getLogger(__name__)

POLL_TIMEOUT_SECONDS = 10


def poll_tenant_config(db: Session, tenant: Tenant) -> bool:
    """Fetch current config from platform and apply if newer. Returns True if applied."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    signing_input = f"{timestamp}|{tenant.slug}".encode("utf-8")
    signature = hmac.new(
        settings.platform_api_secret.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).hexdigest()

    url = f"{settings.platform_base_url.rstrip('/')}/v1/internal/tenants/{tenant.slug}/config"
    headers = {
        "X-Platform-Auth": signature,
        "X-Platform-Timestamp": timestamp,
    }

    try:
        resp = httpx.get(url, headers=headers, timeout=POLL_TIMEOUT_SECONDS)
    except httpx.HTTPError as e:
        logger.warning("platform_sync poll failed for tenant %s: %s", tenant.slug, e)
        return False

    if not (200 <= resp.status_code < 300):
        logger.warning(
            "platform_sync poll non-2xx for tenant %s: %s %s",
            tenant.slug, resp.status_code, resp.text[:200],
        )
        return False

    try:
        body = resp.json()
        payload = PlatformConfigPayload(
            tenant_id=tenant.id,
            default_currency_code=body["default_currency_code"],
            currency_exponent=body["currency_exponent"],
            currency_symbol_override=body.get("currency_symbol_override"),
            synced_at=body["synced_at"],
        )
    except (KeyError, ValueError, TypeError) as e:
        logger.warning("platform_sync invalid response for tenant %s: %s", tenant.slug, e)
        return False

    result = apply_platform_config(db, payload)
    return result.get("applied", False)
