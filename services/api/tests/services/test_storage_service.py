import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.models import Tenant


@pytest.fixture()
def platform_tenant(db, tenant: Tenant) -> Tenant:
    tenant.storage_mode = "platform"
    db.commit()
    return tenant


@pytest.fixture()
def byo_tenant(db, tenant: Tenant) -> Tenant:
    from app.services.email_service import encrypt_secret
    tenant.storage_mode = "byo"
    tenant.byo_storage_endpoint = "https://abc123.r2.cloudflarestorage.com"
    tenant.byo_storage_bucket = "my-store-media"
    tenant.byo_storage_access_key = encrypt_secret("byo_access_key")
    tenant.byo_storage_secret_key = encrypt_secret("byo_secret_key")
    tenant.byo_storage_public_url = "https://media.mystore.com"
    tenant.byo_storage_region = "auto"
    db.commit()
    return tenant


def test_platform_mode_uses_platform_credentials(platform_tenant: Tenant) -> None:
    from app.services.storage_service import get_s3_client_for_tenant
    with patch("boto3.client") as mock_boto:
        mock_boto.return_value = MagicMock()
        get_s3_client_for_tenant(platform_tenant)
    mock_boto.assert_called_once()
    call_kwargs = mock_boto.call_args.kwargs
    assert "endpoint_url" in call_kwargs


def test_byo_mode_uses_tenant_credentials(byo_tenant: Tenant) -> None:
    from app.services.storage_service import get_s3_client_for_tenant
    with patch("boto3.client") as mock_boto:
        mock_boto.return_value = MagicMock()
        get_s3_client_for_tenant(byo_tenant)
    call_kwargs = mock_boto.call_args.kwargs
    assert call_kwargs["endpoint_url"] == "https://abc123.r2.cloudflarestorage.com"
    assert call_kwargs["aws_access_key_id"] == "byo_access_key"


def test_platform_key_includes_tenant_id(platform_tenant: Tenant) -> None:
    from app.services.storage_service import build_object_key
    key = build_object_key(platform_tenant, "products/abc", "photo.jpg")
    assert str(platform_tenant.id) in key
    assert key.endswith(".jpg")


def test_byo_key_excludes_tenant_id(byo_tenant: Tenant) -> None:
    from app.services.storage_service import build_object_key
    key = build_object_key(byo_tenant, "products/abc", "photo.jpg")
    assert str(byo_tenant.id) not in key
    assert "products/abc" in key


def test_public_url_platform_uses_r2_public_url(platform_tenant: Tenant) -> None:
    from app.services.storage_service import build_public_url
    with patch("app.services.storage_service.settings") as mock_settings:
        mock_settings.r2_public_url = "https://media.platform.com"
        url = build_public_url(platform_tenant, "abc/photo.jpg")
    assert url == "https://media.platform.com/abc/photo.jpg"


def test_public_url_byo_uses_tenant_cdn(byo_tenant: Tenant) -> None:
    from app.services.storage_service import build_public_url
    url = build_public_url(byo_tenant, "products/abc/photo.jpg")
    assert url == "https://media.mystore.com/products/abc/photo.jpg"


def test_presign_upload_returns_url_and_public_url(platform_tenant: Tenant) -> None:
    from app.services.storage_service import presign_upload

    mock_s3 = MagicMock()
    mock_s3.generate_presigned_url.return_value = "https://r2.example.com/presigned"

    with patch("app.services.storage_service.get_s3_client_for_tenant", return_value=mock_s3), \
         patch("app.services.storage_service.settings") as mock_settings:
        mock_settings.r2_public_url = "https://media.platform.com"
        mock_settings.r2_bucket_name = "ims-media"
        mock_settings.r2_endpoint_url = "https://xxx.r2.cloudflarestorage.com"
        result = presign_upload(
            tenant=platform_tenant,
            folder="products/abc",
            filename="hero.jpg",
            content_type="image/jpeg",
        )

    assert result["upload_url"] == "https://r2.example.com/presigned"
    assert result["public_url"].startswith("https://media.platform.com/")
    assert "key" in result
    assert result["expires_in"] == 900


def test_presign_upload_rejects_unsupported_type(platform_tenant: Tenant) -> None:
    from app.services.storage_service import presign_upload
    with patch("app.services.storage_service.settings") as mock_settings:
        mock_settings.r2_endpoint_url = "https://xxx.r2.cloudflarestorage.com"
        mock_settings.r2_bucket_name = "ims-media"
        with pytest.raises(ValueError, match="not allowed"):
            presign_upload(
                tenant=platform_tenant,
                folder="products/abc",
                filename="doc.pdf",
                content_type="application/pdf",
            )
