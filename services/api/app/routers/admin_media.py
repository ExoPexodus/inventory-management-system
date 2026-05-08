"""Admin endpoint for getting presigned upload URLs for direct browser-to-R2 uploads."""
from __future__ import annotations

import math
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Tenant, TenantLicenseCache
from app.services.storage_service import presign_upload

router = APIRouter(
    prefix="/v1/admin/media",
    tags=["Media Upload"],
    dependencies=[require_permission("catalog:write")],
)


class PresignIn(BaseModel):
    folder: str = Field(min_length=1, max_length=255)
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=64)
    file_size_bytes: int = Field(ge=1)


class StorageWarning(BaseModel):
    used_pct: int
    used_mb: int
    limit_mb: int


class PresignOut(BaseModel):
    upload_url: str
    public_url: str
    key: str
    expires_in: int
    content_type: str
    storage_warning: StorageWarning | None = None


class _StorageQuotaExceeded(Exception):
    """Internal signal raised by _check_quota when the hard limit is hit."""
    def __init__(self, used_bytes: int, limit_bytes: int, detail: str) -> None:
        self.used_bytes = used_bytes
        self.limit_bytes = limit_bytes
        self.detail = detail


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Operator not assigned to a tenant")
    return ctx.tenant_id


def _check_quota(tenant: Tenant, file_size_bytes: int, db: Session) -> StorageWarning | None:
    """Check storage quota. Raises _StorageQuotaExceeded if over limit. Returns StorageWarning if >= 80%."""
    if tenant.storage_mode == "byo":
        return None

    cache: TenantLicenseCache | None = db.execute(
        select(TenantLicenseCache).where(TenantLicenseCache.tenant_id == tenant.id)
    ).scalar_one_or_none()

    if cache is None:
        return None

    limit_bytes = cache.storage_limit_mb * 1_048_576
    used_bytes = tenant.storage_bytes_used
    projected = used_bytes + file_size_bytes

    if projected > limit_bytes:
        used_mb = math.ceil(used_bytes / 1_048_576)
        limit_mb = cache.storage_limit_mb
        raise _StorageQuotaExceeded(
            used_bytes=used_bytes,
            limit_bytes=limit_bytes,
            detail=(
                f"Storage limit reached. You have used {used_mb} MB "
                f"of your {limit_mb} MB limit."
            ),
        )

    if limit_bytes > 0 and projected / limit_bytes >= 0.80:
        used_pct = math.ceil(projected / limit_bytes * 100)
        return StorageWarning(
            used_pct=used_pct,
            used_mb=math.ceil(projected / 1_048_576),
            limit_mb=cache.storage_limit_mb,
        )

    return None


@router.post("/presign-upload", response_model=PresignOut)
def get_presign_upload_url(
    body: PresignIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> PresignOut:
    """Get a presigned PUT URL for uploading an image directly to R2."""
    tenant_id = _require_tenant(ctx)
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    try:
        warning = _check_quota(tenant, body.file_size_bytes, db)
    except _StorageQuotaExceeded as exc:
        return JSONResponse(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            content={
                "detail": exc.detail,
                "used_bytes": exc.used_bytes,
                "limit_bytes": exc.limit_bytes,
            },
        )

    try:
        result = presign_upload(
            tenant=tenant,
            folder=body.folder.strip("/"),
            filename=body.filename,
            content_type=body.content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return PresignOut(**result, storage_warning=warning)
