"""Tests for the app_updates router — OTA update check and download proxy."""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminContext
from app.auth.deps import DeviceAuth
from app.config import settings
from app.models import Tenant
from app.routers.app_updates import (
    DownloadsOut,
    UpdateCheckOut,
    admin_app_download,
    admin_downloads,
    device_app_download,
    update_check,
)


def _device_ctx(tenant_id) -> DeviceAuth:
    return DeviceAuth(device_id=uuid.uuid4(), tenant_id=tenant_id, shop_ids=[])


def _admin_ctx(tenant_id) -> AdminContext:
    return AdminContext(
        user_id=None, tenant_id=tenant_id, role="admin",
        role_id=None, is_legacy_token=False, permissions=frozenset(),
    )


_SAMPLE_MANIFEST = [
    {
        "app_name": "cashier", "display_name": "Cashier POS", "description": "POS app",
        "version": "1.2.0", "version_code": 12, "changelog": "Bug fixes",
        "size_mb": 45.3, "available": True,
    },
    {
        "app_name": "admin_mobile", "display_name": "Admin Mobile", "description": "Admin app",
        "version": "1.0.5", "version_code": 5, "changelog": "Improvements",
        "size_mb": 38.1, "available": True,
    },
]


def test_update_check_unknown_app_name_raises_400(db: Session, tenant: Tenant) -> None:
    with pytest.raises(HTTPException) as exc:
        update_check(ctx=_device_ctx(tenant.id), db=db, app_name="unknown_app")
    assert exc.value.status_code == 400


def test_update_check_no_download_token_returns_unavailable(db: Session, tenant: Tenant) -> None:
    tenant.download_token = None
    db.commit()
    result = update_check(ctx=_device_ctx(tenant.id), db=db, app_name="cashier")
    assert result.available is False
    assert result.version is None
    assert result.download_url is None


def test_update_check_platform_error_returns_unavailable(db: Session, tenant: Tenant) -> None:
    tenant.download_token = "test-token-abc"
    db.commit()
    with patch("app.routers.app_updates._fetch_manifest", return_value=[]):
        result = update_check(ctx=_device_ctx(tenant.id), db=db, app_name="cashier")
    assert result.available is False


def test_update_check_returns_full_info(db: Session, tenant: Tenant) -> None:
    tenant.download_token = "test-token-abc"
    db.commit()
    with patch("app.routers.app_updates._fetch_manifest", return_value=_SAMPLE_MANIFEST):
        result = update_check(ctx=_device_ctx(tenant.id), db=db, app_name="cashier")
    assert result.available is True
    assert result.version == "1.2.0"
    assert result.version_code == 12
    assert result.changelog == "Bug fixes"
    assert result.size_mb == 45.3
    assert result.download_url is not None
    assert "/v1/apps/cashier/download" in result.download_url


def test_update_check_admin_mobile(db: Session, tenant: Tenant) -> None:
    tenant.download_token = "test-token-abc"
    db.commit()
    with patch("app.routers.app_updates._fetch_manifest", return_value=_SAMPLE_MANIFEST):
        result = update_check(ctx=_device_ctx(tenant.id), db=db, app_name="admin_mobile")
    assert result.available is True
    assert result.version_code == 5
    assert "/v1/apps/admin_mobile/download" in result.download_url


def test_admin_downloads_no_token_returns_empty(db: Session, tenant: Tenant) -> None:
    tenant.download_token = None
    db.commit()
    result = admin_downloads(ctx=_admin_ctx(tenant.id), db=db)
    assert isinstance(result, DownloadsOut)
    assert result.download_page_url == ""
    assert result.apps == []


def test_admin_downloads_returns_page_url_and_both_apps(db: Session, tenant: Tenant) -> None:
    tenant.download_token = "tok123"
    db.commit()
    with patch("app.routers.app_updates._fetch_manifest", return_value=_SAMPLE_MANIFEST):
        result = admin_downloads(ctx=_admin_ctx(tenant.id), db=db)
    assert "tok123" in result.download_page_url
    assert len(result.apps) == 2
    cashier = next(a for a in result.apps if a.app_name == "cashier")
    assert cashier.version == "1.2.0"
    assert cashier.admin_download_url == "/v1/admin/apps/cashier/download"


def test_device_app_download_no_token_raises_404(db: Session, tenant: Tenant) -> None:
    tenant.download_token = None
    db.commit()
    with pytest.raises(HTTPException) as exc:
        device_app_download(app_name="cashier", ctx=_device_ctx(tenant.id), db=db)
    assert exc.value.status_code == 404


def test_admin_app_download_redirects(db: Session, tenant: Tenant) -> None:
    tenant.download_token = "tok123"
    db.commit()
    with patch.object(settings, "platform_download_base_url", "http://platform.example.com"):
        result = admin_app_download(app_name="cashier", ctx=_admin_ctx(tenant.id), db=db)
    assert isinstance(result, RedirectResponse)
    assert result.status_code == 302
    location = result.headers.get("location", "")
    assert "tok123" in location
    assert "cashier" in location


def test_device_app_download_redirects(db: Session, tenant: Tenant) -> None:
    tenant.download_token = "tok456"
    db.commit()
    with patch.object(settings, "platform_download_base_url", "http://platform.example.com"):
        result = device_app_download(app_name="cashier", ctx=_device_ctx(tenant.id), db=db)
    assert isinstance(result, RedirectResponse)
    assert result.status_code == 302
    location = result.headers.get("location", "")
    assert "tok456" in location
    assert "cashier" in location


def test_device_app_download_503_when_no_download_base_url(db: Session, tenant: Tenant) -> None:
    tenant.download_token = "tok789"
    db.commit()
    with patch.object(settings, "platform_download_base_url", ""):
        with pytest.raises(HTTPException) as exc:
            device_app_download(app_name="cashier", ctx=_device_ctx(tenant.id), db=db)
    assert exc.value.status_code == 503


def test_admin_downloads_no_tenant_context_raises_403(db: Session) -> None:
    ctx = AdminContext(
        user_id=None, tenant_id=None, role=None,
        role_id=None, is_legacy_token=False, permissions=frozenset(),
    )
    with pytest.raises(HTTPException) as exc:
        admin_downloads(ctx=ctx, db=db)
    assert exc.value.status_code == 403


def test_admin_app_download_no_tenant_context_raises_403(db: Session) -> None:
    ctx = AdminContext(
        user_id=None, tenant_id=None, role=None,
        role_id=None, is_legacy_token=False, permissions=frozenset(),
    )
    with pytest.raises(HTTPException) as exc:
        admin_app_download(app_name="cashier", ctx=ctx, db=db)
    assert exc.value.status_code == 403
