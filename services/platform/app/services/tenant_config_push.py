"""Push tenant configuration to api service via HMAC-signed HTTP call."""
from __future__ import annotations

import hmac
import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from app.config import settings
from app.models import PlatformTenant

logger = logging.getLogger(__name__)

PUSH_TIMEOUT_SECONDS = 10


@dataclass
class PushResult:
    status: str  # "success" | "failed"
    error: str | None = None
    applied: bool | None = None


def push_tenant_currency_config(tenant: PlatformTenant) -> PushResult:
    """POST currency config to the tenant's api_base_url. Single attempt, no retry."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    signing_input = f"{timestamp}|{tenant.id}".encode("utf-8")
    signature = hmac.new(
        settings.jwt_secret.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).hexdigest()

    url = f"{tenant.api_base_url.rstrip('/')}/v1/internal/platform-config"
    body = {
        "tenant_id": str(tenant.id),
        "default_currency_code": tenant.default_currency_code,
        "currency_exponent": tenant.currency_exponent,
        "currency_symbol_override": tenant.currency_symbol_override,
        "synced_at": timestamp,
    }
    headers = {
        "X-Platform-Auth": signature,
        "X-Platform-Timestamp": timestamp,
        "Content-Type": "application/json",
    }

    try:
        resp = httpx.post(url, json=body, headers=headers, timeout=PUSH_TIMEOUT_SECONDS)
    except httpx.TimeoutException:
        logger.warning("tenant_config_push timeout for tenant %s", tenant.slug)
        return PushResult(status="failed", error="push request timeout")
    except httpx.HTTPError as e:
        logger.warning("tenant_config_push http error for tenant %s: %s", tenant.slug, e)
        return PushResult(status="failed", error=f"http error: {e}")

    if not (200 <= resp.status_code < 300):
        logger.warning(
            "tenant_config_push non-2xx for tenant %s: %s",
            tenant.slug, resp.status_code,
        )
        return PushResult(status="failed", error=f"{resp.status_code}: {resp.text[:200]}")

    try:
        resp_body = resp.json()
        applied = resp_body.get("applied")
    except Exception:
        applied = None

    return PushResult(status="success", applied=applied)
