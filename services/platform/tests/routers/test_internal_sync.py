from __future__ import annotations

import hmac
import hashlib
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.models import PlatformTenant
from app.routers.internal_sync import get_tenant_config_internal


def _hmac_headers(slug: str) -> dict:
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    sig = hmac.new(
        settings.jwt_secret.encode("utf-8"),
        f"{timestamp}|{slug}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {"X-Platform-Auth": sig, "X-Platform-Timestamp": timestamp}


def _mock_request(headers: dict) -> Mock:
    req = Mock()
    req.headers = headers
    return req


def test_get_config_returns_currency_with_valid_hmac(
    db: Session, platform_tenant: PlatformTenant,
) -> None:
    platform_tenant.default_currency_code = "INR"
    platform_tenant.currency_exponent = 2
    db.commit()

    request = _mock_request(_hmac_headers(platform_tenant.slug))
    result = get_tenant_config_internal(slug=platform_tenant.slug, request=request, db=db)

    assert result.default_currency_code == "INR"
    assert result.currency_exponent == 2


def test_get_config_rejects_missing_hmac(db: Session, platform_tenant: PlatformTenant) -> None:
    request = _mock_request({})
    with pytest.raises(HTTPException) as exc:
        get_tenant_config_internal(slug=platform_tenant.slug, request=request, db=db)
    assert exc.value.status_code == 401


def test_get_config_rejects_invalid_hmac(db: Session, platform_tenant: PlatformTenant) -> None:
    request = _mock_request({
        "X-Platform-Auth": "deadbeef" * 8,  # 64 chars, wrong value
        "X-Platform-Timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    with pytest.raises(HTTPException) as exc:
        get_tenant_config_internal(slug=platform_tenant.slug, request=request, db=db)
    assert exc.value.status_code == 401


def test_get_config_rejects_stale_timestamp(db: Session, platform_tenant: PlatformTenant) -> None:
    stale_ts = "2020-01-01T00:00:00Z"
    sig = hmac.new(
        settings.jwt_secret.encode("utf-8"),
        f"{stale_ts}|{platform_tenant.slug}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    request = _mock_request({"X-Platform-Auth": sig, "X-Platform-Timestamp": stale_ts})

    with pytest.raises(HTTPException) as exc:
        get_tenant_config_internal(slug=platform_tenant.slug, request=request, db=db)
    assert exc.value.status_code == 401


def test_get_config_401_for_unknown_slug(db: Session, platform_tenant: PlatformTenant) -> None:
    """Unknown slug returns 401 (same as invalid HMAC) to avoid leaking tenant existence."""
    request = _mock_request(_hmac_headers("does-not-exist"))
    with pytest.raises(HTTPException) as exc:
        get_tenant_config_internal(slug="does-not-exist", request=request, db=db)
    assert exc.value.status_code == 401
