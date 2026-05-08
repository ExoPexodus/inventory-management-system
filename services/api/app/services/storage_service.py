"""Cloudflare R2 / S3-compatible image storage service.

Two modes per tenant:
  "platform" — IMS-managed R2 bucket. Key = {tenant_id}/{folder}/{uuid}.{ext}
  "byo"      — Tenant's own bucket.   Key = {folder}/{uuid}.{ext}

Upload flow:
  1. Frontend calls POST /v1/admin/media/presign-upload → gets { upload_url, public_url, key }
  2. Frontend PUT file bytes directly to upload_url (never hits our API server)
  3. Frontend calls POST /v1/admin/catalog/products/{id}/images with public_url
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config

from app.config import settings
from app.services.email_service import decrypt_secret

logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES = frozenset({
    "image/jpeg", "image/png", "image/webp", "image/gif", "image/avif",
})
MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
PRESIGN_TTL_SECONDS = 900          # 15 minutes


def get_s3_client_for_tenant(tenant) -> Any:
    """Return a boto3 S3 client configured for the tenant's storage mode."""
    if tenant.storage_mode == "byo":
        access_key = decrypt_secret(tenant.byo_storage_access_key) or ""
        secret_key = decrypt_secret(tenant.byo_storage_secret_key) or ""
        return boto3.client(
            "s3",
            endpoint_url=tenant.byo_storage_endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=tenant.byo_storage_region or "auto",
            config=Config(signature_version="s3v4"),
        )
    # Platform mode
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name=settings.r2_region or "auto",
        config=Config(signature_version="s3v4"),
    )


def get_bucket_name(tenant) -> str:
    if tenant.storage_mode == "byo":
        return tenant.byo_storage_bucket or ""
    return settings.r2_bucket_name


def build_object_key(tenant, folder: str, filename: str) -> str:
    """Build the storage object key.

    Platform: {tenant_id}/{folder}/{uuid}.{ext}
    BYO:      {folder}/{uuid}.{ext}
    """
    ext = Path(filename).suffix.lower() or ".bin"
    unique = uuid.uuid4().hex
    path = f"{folder}/{unique}{ext}"
    if tenant.storage_mode == "platform":
        return f"{tenant.id}/{path}"
    return path


def build_public_url(tenant, key: str) -> str:
    """Build the public CDN URL for an object key."""
    if tenant.storage_mode == "byo":
        base = (tenant.byo_storage_public_url or "").rstrip("/")
    else:
        base = settings.r2_public_url.rstrip("/")
    return f"{base}/{key}"


def presign_upload(
    tenant,
    folder: str,
    filename: str,
    content_type: str,
) -> dict:
    """Generate a presigned PUT URL for direct browser-to-R2 upload.

    Returns: { upload_url, public_url, key, expires_in, content_type }
    Raises ValueError if content_type not allowed or storage not configured.
    """
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError(
            f"Content type {content_type!r} not allowed. "
            f"Accepted: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
        )

    bucket = get_bucket_name(tenant)
    if not bucket:
        raise ValueError(
            f"Storage not configured for tenant {tenant.id} "
            f"(mode={tenant.storage_mode!r})"
        )

    if tenant.storage_mode == "platform" and not settings.r2_endpoint_url:
        raise ValueError(
            "Platform R2 storage is not configured. "
            "Set R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, "
            "R2_BUCKET_NAME, and R2_PUBLIC_URL environment variables."
        )

    key = build_object_key(tenant, folder, filename)
    s3 = get_s3_client_for_tenant(tenant)

    upload_url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=PRESIGN_TTL_SECONDS,
    )

    return {
        "upload_url": upload_url,
        "public_url": build_public_url(tenant, key),
        "key": key,
        "expires_in": PRESIGN_TTL_SECONDS,
        "content_type": content_type,
    }


def sum_r2_prefix(prefix: str) -> int:
    """Return the total bytes of all objects under a key prefix in the platform R2 bucket.

    Paginates automatically. Returns 0 if the platform bucket is not configured
    or the prefix has no objects.
    """
    if not settings.r2_endpoint_url or not settings.r2_bucket_name:
        logger.debug("Platform R2 not configured — sum_r2_prefix returning 0")
        return 0

    s3 = boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name=settings.r2_region or "auto",
        config=Config(signature_version="s3v4"),
    )

    total_bytes = 0
    continuation_token: str | None = None

    while True:
        kwargs: dict = {"Bucket": settings.r2_bucket_name, "Prefix": prefix}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token

        resp = s3.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []):
            total_bytes += obj.get("Size", 0)

        if resp.get("IsTruncated"):
            continuation_token = resp.get("NextContinuationToken")
        else:
            break

    return total_bytes
