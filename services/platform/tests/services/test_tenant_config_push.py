from __future__ import annotations

import hmac
import hashlib
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session

from app.config import settings
from app.models import PlatformTenant
from app.services.tenant_config_push import push_tenant_currency_config


def test_push_succeeds_on_2xx(platform_tenant: PlatformTenant) -> None:
    platform_tenant.default_currency_code = "INR"
    platform_tenant.currency_exponent = 2
    platform_tenant.currency_symbol_override = None

    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"applied": True}

    with patch("app.services.tenant_config_push.httpx.post", return_value=mock_resp) as mock_post:
        result = push_tenant_currency_config(platform_tenant)
        assert result.status == "success"
        mock_post.assert_called_once()
        url = mock_post.call_args.args[0]
        assert platform_tenant.api_base_url in url
        headers = mock_post.call_args.kwargs["headers"]
        assert "X-Platform-Auth" in headers
        assert "X-Platform-Timestamp" in headers
        body = mock_post.call_args.kwargs["json"]
        assert body["tenant_id"] == str(platform_tenant.id)
        assert body["default_currency_code"] == "INR"
        assert body["currency_exponent"] == 2


def test_push_returns_failed_status_on_5xx(platform_tenant: PlatformTenant) -> None:
    mock_resp = Mock()
    mock_resp.status_code = 500
    mock_resp.text = "internal error"

    with patch("app.services.tenant_config_push.httpx.post", return_value=mock_resp):
        result = push_tenant_currency_config(platform_tenant)
        assert result.status == "failed"
        assert "500" in (result.error or "")


def test_push_returns_failed_status_on_timeout(platform_tenant: PlatformTenant) -> None:
    import httpx

    with patch("app.services.tenant_config_push.httpx.post", side_effect=httpx.TimeoutException("timed out")):
        result = push_tenant_currency_config(platform_tenant)
        assert result.status == "failed"
        assert "timeout" in (result.error or "").lower()


def test_push_signs_with_global_jwt_secret(platform_tenant: PlatformTenant) -> None:
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"applied": True}

    with patch("app.services.tenant_config_push.httpx.post", return_value=mock_resp) as mock_post:
        push_tenant_currency_config(platform_tenant)

        headers = mock_post.call_args.kwargs["headers"]
        timestamp = headers["X-Platform-Timestamp"]
        expected_sig = hmac.new(
            settings.jwt_secret.encode("utf-8"),
            f"{timestamp}|{platform_tenant.id}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert headers["X-Platform-Auth"] == expected_sig
