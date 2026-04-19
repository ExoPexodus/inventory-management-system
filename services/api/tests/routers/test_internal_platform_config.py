from __future__ import annotations

import hmac
import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Tenant
from app.routers.internal_sync import (
    PlatformConfigPayload,
    apply_platform_config,
    verify_push_hmac,
)


def test_apply_newer_config_updates_tenant_and_returns_applied(
    db: Session, tenant: Tenant,
) -> None:
    payload = PlatformConfigPayload(
        tenant_id=tenant.id,
        default_currency_code="INR",
        currency_exponent=2,
        currency_symbol_override="Rs",
        synced_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    result = apply_platform_config(db, payload)
    db.refresh(tenant)

    assert result["applied"] is True
    assert tenant.default_currency_code == "INR"
    assert tenant.currency_exponent == 2
    assert tenant.currency_symbol_override == "Rs"
    assert tenant.currency_synced_at is not None


def test_apply_older_config_is_noop(db: Session, tenant: Tenant) -> None:
    tenant.default_currency_code = "USD"
    tenant.currency_synced_at = datetime.now(UTC)
    db.commit()

    older_ts = "2020-01-01T00:00:00Z"
    payload = PlatformConfigPayload(
        tenant_id=tenant.id,
        default_currency_code="INR",
        currency_exponent=2,
        currency_symbol_override=None,
        synced_at=older_ts,
    )
    result = apply_platform_config(db, payload)
    db.refresh(tenant)

    assert result["applied"] is False
    assert tenant.default_currency_code == "USD"


def test_verify_hmac_accepts_valid_signature(tenant: Tenant) -> None:
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    sig = hmac.new(
        settings.platform_api_secret.encode("utf-8"),
        f"{timestamp}|{tenant.id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    # Should not raise
    verify_push_hmac(signature=sig, timestamp=timestamp, tenant_id=str(tenant.id))


def test_verify_hmac_rejects_invalid_signature(tenant: Tenant) -> None:
    with pytest.raises(HTTPException) as exc:
        verify_push_hmac(
            signature="deadbeef" * 8,
            timestamp=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            tenant_id=str(tenant.id),
        )
    assert exc.value.status_code == 401


def test_verify_hmac_rejects_missing_headers(tenant: Tenant) -> None:
    with pytest.raises(HTTPException) as exc:
        verify_push_hmac(signature=None, timestamp=None, tenant_id=str(tenant.id))
    assert exc.value.status_code == 401


def test_verify_hmac_rejects_stale_timestamp(tenant: Tenant) -> None:
    stale_ts = "2020-01-01T00:00:00Z"
    sig = hmac.new(
        settings.platform_api_secret.encode("utf-8"),
        f"{stale_ts}|{tenant.id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    with pytest.raises(HTTPException) as exc:
        verify_push_hmac(signature=sig, timestamp=stale_ts, tenant_id=str(tenant.id))
    assert exc.value.status_code == 401


def test_apply_404_for_unknown_tenant(db: Session) -> None:
    payload = PlatformConfigPayload(
        tenant_id=uuid4(),
        default_currency_code="INR",
        currency_exponent=2,
        currency_symbol_override=None,
        synced_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    with pytest.raises(HTTPException) as exc:
        apply_platform_config(db, payload)
    assert exc.value.status_code == 404
