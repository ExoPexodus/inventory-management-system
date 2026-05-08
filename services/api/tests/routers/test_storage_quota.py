# NOTE: `from __future__ import annotations` deliberately absent.

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Tenant, TenantLicenseCache


@pytest.fixture()
def auth(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin
    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id, role="owner", role_id=None,
        is_legacy_token=False, permissions=frozenset({"catalog:write"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
def tenant_with_license(db, tenant: Tenant) -> Tenant:
    """Platform-mode tenant with a 10 MB storage limit."""
    tenant.storage_mode = "platform"
    tenant.storage_bytes_used = 0
    import datetime
    cache = TenantLicenseCache(
        tenant_id=tenant.id,
        subscription_status="active",
        plan_codename="trial",
        storage_limit_mb=10,
        max_shops=1,
        max_employees=5,
        last_synced_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db.add(cache)
    db.commit()
    return tenant


def _presign(client, file_size_bytes=1024):
    with patch("app.routers.admin_media.presign_upload") as mock:
        mock.return_value = {
            "upload_url": "https://r2.example.com/presigned",
            "public_url": "https://media.example.com/key.jpg",
            "key": "tenant/products/abc/abc.jpg",
            "expires_in": 900,
            "content_type": "image/jpeg",
        }
        return client.post("/v1/admin/media/presign-upload", json={
            "folder": "products/abc",
            "filename": "img.jpg",
            "content_type": "image/jpeg",
            "file_size_bytes": file_size_bytes,
        })


def test_presign_succeeds_under_quota(db, tenant_with_license: Tenant, auth) -> None:
    resp = _presign(TestClient(app), file_size_bytes=100)
    assert resp.status_code == 200, resp.text
    assert resp.json()["storage_warning"] is None


def test_presign_returns_warning_at_80_percent(db, tenant_with_license: Tenant, auth) -> None:
    limit_bytes = 10 * 1024 * 1024
    tenant_with_license.storage_bytes_used = int(limit_bytes * 0.85)
    db.commit()

    resp = _presign(TestClient(app), file_size_bytes=1024)
    assert resp.status_code == 200, resp.text
    warning = resp.json()["storage_warning"]
    assert warning is not None
    assert warning["used_pct"] >= 80
    assert warning["limit_mb"] == 10


def test_presign_blocked_at_100_percent(db, tenant_with_license: Tenant, auth) -> None:
    limit_bytes = 10 * 1024 * 1024
    tenant_with_license.storage_bytes_used = limit_bytes
    db.commit()

    resp = _presign(TestClient(app), file_size_bytes=1024)
    assert resp.status_code == 402
    body = resp.json()
    assert "limit reached" in body["detail"].lower()
    assert "used_bytes" in body
    assert "limit_bytes" in body


def test_presign_byo_tenant_skips_quota(db, tenant: Tenant, auth) -> None:
    tenant.storage_mode = "byo"
    tenant.storage_bytes_used = 999_999_999_999
    db.commit()

    resp = _presign(TestClient(app), file_size_bytes=1024)
    assert resp.status_code != 402


def test_presign_no_license_cache_skips_quota(db, tenant: Tenant, auth) -> None:
    tenant.storage_mode = "platform"
    tenant.storage_bytes_used = 0
    db.commit()

    resp = _presign(TestClient(app), file_size_bytes=1024)
    assert resp.status_code != 402
