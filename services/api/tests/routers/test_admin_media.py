# NOTE: `from __future__ import annotations` deliberately absent.

from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Tenant


@pytest.fixture()
def auth(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin
    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id, role="owner", role_id=None,
        is_legacy_token=False, permissions=frozenset({"catalog:write", "settings:read"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield
    app.dependency_overrides.clear()


def test_presign_upload_returns_urls(db, tenant: Tenant, auth) -> None:
    with patch("app.routers.admin_media.presign_upload") as mock_presign:
        mock_presign.return_value = {
            "upload_url": "https://r2.example.com/presigned",
            "public_url": "https://media.platform.com/tenant/products/abc/file.jpg",
            "key": f"{tenant.id}/products/abc/file.jpg",
            "expires_in": 900,
            "content_type": "image/jpeg",
        }
        resp = TestClient(app).post("/v1/admin/media/presign-upload", json={
            "folder": "products/abc",
            "filename": "hero.jpg",
            "content_type": "image/jpeg",
            "file_size_bytes": 1024,
        })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "upload_url" in body
    assert "public_url" in body
    assert body["expires_in"] == 900


def test_presign_upload_rejects_unsupported_type(db, tenant: Tenant, auth) -> None:
    with patch("app.routers.admin_media.presign_upload",
               side_effect=ValueError("Content type 'application/pdf' not allowed")):
        resp = TestClient(app).post("/v1/admin/media/presign-upload", json={
            "folder": "products/abc",
            "filename": "document.pdf",
            "content_type": "application/pdf",
            "file_size_bytes": 1024,
        })
    assert resp.status_code == 400
    assert "not allowed" in resp.json()["detail"]


def test_get_storage_config_platform_default(db, tenant: Tenant, auth) -> None:
    resp = TestClient(app).get("/v1/admin/tenant-settings/storage")
    assert resp.status_code == 200
    assert resp.json()["storage_mode"] == "platform"
    assert resp.json()["has_access_key"] is False


def test_configure_byo_storage(db, tenant: Tenant, auth) -> None:
    from app.services.email_service import decrypt_secret
    resp = TestClient(app).put("/v1/admin/tenant-settings/storage", json={
        "storage_mode": "byo",
        "byo_storage_endpoint": "https://abc.r2.cloudflarestorage.com",
        "byo_storage_bucket": "my-bucket",
        "byo_storage_access_key": "AK123",
        "byo_storage_secret_key": "SK456",
        "byo_storage_public_url": "https://media.mystore.com",
        "byo_storage_region": "auto",
    })
    assert resp.status_code == 200, resp.text
    db.refresh(tenant)
    assert tenant.storage_mode == "byo"
    assert tenant.byo_storage_bucket == "my-bucket"
    assert decrypt_secret(tenant.byo_storage_access_key) == "AK123"
    assert decrypt_secret(tenant.byo_storage_secret_key) == "SK456"
    assert resp.json()["has_access_key"] is True


def test_switch_back_to_platform_clears_byo_fields(db, tenant: Tenant, auth) -> None:
    # Set BYO first
    tenant.storage_mode = "byo"
    tenant.byo_storage_bucket = "my-bucket"
    tenant.byo_storage_endpoint = "https://abc.r2.cloudflarestorage.com"
    tenant.byo_storage_public_url = "https://media.mystore.com"
    db.commit()

    resp = TestClient(app).put("/v1/admin/tenant-settings/storage", json={
        "storage_mode": "platform",
    })
    assert resp.status_code == 200
    db.refresh(tenant)
    assert tenant.storage_mode == "platform"
    assert tenant.byo_storage_bucket is None
