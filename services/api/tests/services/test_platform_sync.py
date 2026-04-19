from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session

from app.models import Tenant
from app.services.platform_sync import poll_tenant_config


def test_poll_updates_tenant_on_newer_platform_config(
    db: Session, tenant: Tenant,
) -> None:
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "default_currency_code": "INR",
        "currency_exponent": 2,
        "currency_symbol_override": None,
        "synced_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    with patch("app.services.platform_sync.httpx.get", return_value=mock_resp):
        applied = poll_tenant_config(db, tenant)

    db.refresh(tenant)
    assert applied is True
    assert tenant.default_currency_code == "INR"
    assert tenant.currency_synced_at is not None


def test_poll_skips_when_platform_returns_older_config(
    db: Session, tenant: Tenant,
) -> None:
    tenant.default_currency_code = "USD"
    tenant.currency_synced_at = datetime.now(UTC)
    db.commit()

    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "default_currency_code": "INR",
        "currency_exponent": 2,
        "currency_symbol_override": None,
        "synced_at": "2020-01-01T00:00:00Z",
    }

    with patch("app.services.platform_sync.httpx.get", return_value=mock_resp):
        applied = poll_tenant_config(db, tenant)

    db.refresh(tenant)
    assert applied is False
    assert tenant.default_currency_code == "USD"


def test_poll_returns_false_on_platform_http_error(
    db: Session, tenant: Tenant,
) -> None:
    import httpx

    with patch(
        "app.services.platform_sync.httpx.get",
        side_effect=httpx.HTTPError("platform down"),
    ):
        applied = poll_tenant_config(db, tenant)

    assert applied is False


def test_poll_returns_false_on_non_2xx(db: Session, tenant: Tenant) -> None:
    mock_resp = Mock()
    mock_resp.status_code = 500
    mock_resp.text = "server error"

    with patch("app.services.platform_sync.httpx.get", return_value=mock_resp):
        applied = poll_tenant_config(db, tenant)

    assert applied is False
