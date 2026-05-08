"""Admin endpoints for viewing and updating tenant storage configuration."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Tenant
from app.services.email_service import encrypt_secret

router = APIRouter(
    prefix="/v1/admin/tenant-settings",
    tags=["Tenant Storage Settings"],
)


class StorageConfigOut(BaseModel):
    storage_mode: str
    byo_storage_endpoint: str | None
    byo_storage_bucket: str | None
    byo_storage_public_url: str | None
    byo_storage_region: str | None
    has_access_key: bool
    has_secret_key: bool


class StorageConfigIn(BaseModel):
    storage_mode: str = Field(pattern="^(platform|byo)$")
    byo_storage_endpoint: str | None = Field(default=None, max_length=512)
    byo_storage_bucket: str | None = Field(default=None, max_length=255)
    byo_storage_access_key: str | None = Field(default=None)
    byo_storage_secret_key: str | None = Field(default=None)
    byo_storage_public_url: str | None = Field(default=None, max_length=512)
    byo_storage_region: str | None = Field(default=None, max_length=32)


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Operator not assigned to a tenant")
    return ctx.tenant_id


@router.get("/storage", response_model=StorageConfigOut,
            dependencies=[require_permission("settings:read")])
def get_storage_config(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> StorageConfigOut:
    tenant_id = _require_tenant(ctx)
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return StorageConfigOut(
        storage_mode=tenant.storage_mode,
        byo_storage_endpoint=tenant.byo_storage_endpoint,
        byo_storage_bucket=tenant.byo_storage_bucket,
        byo_storage_public_url=tenant.byo_storage_public_url,
        byo_storage_region=tenant.byo_storage_region,
        has_access_key=bool(tenant.byo_storage_access_key),
        has_secret_key=bool(tenant.byo_storage_secret_key),
    )


@router.put("/storage", response_model=StorageConfigOut,
            dependencies=[require_permission("settings:write")])
def update_storage_config(
    body: StorageConfigIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> StorageConfigOut:
    tenant_id = _require_tenant(ctx)
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if body.storage_mode == "byo":
        if not body.byo_storage_endpoint or not body.byo_storage_bucket:
            raise HTTPException(status_code=400,
                detail="byo_storage_endpoint and byo_storage_bucket are required for BYO mode")
        if not body.byo_storage_public_url:
            raise HTTPException(status_code=400,
                detail="byo_storage_public_url is required for BYO mode")

    if body.storage_mode == "platform":
        # Clear all BYO fields when switching back to platform
        tenant.storage_mode = "platform"
        tenant.byo_storage_endpoint = None
        tenant.byo_storage_bucket = None
        tenant.byo_storage_access_key = None
        tenant.byo_storage_secret_key = None
        tenant.byo_storage_public_url = None
        tenant.byo_storage_region = None
    else:
        tenant.storage_mode = "byo"
        tenant.byo_storage_endpoint = body.byo_storage_endpoint
        tenant.byo_storage_bucket = body.byo_storage_bucket
        tenant.byo_storage_public_url = body.byo_storage_public_url
        tenant.byo_storage_region = body.byo_storage_region
        if body.byo_storage_access_key:
            tenant.byo_storage_access_key = encrypt_secret(body.byo_storage_access_key)
        if body.byo_storage_secret_key:
            tenant.byo_storage_secret_key = encrypt_secret(body.byo_storage_secret_key)

    db.commit()
    db.refresh(tenant)
    return StorageConfigOut(
        storage_mode=tenant.storage_mode,
        byo_storage_endpoint=tenant.byo_storage_endpoint,
        byo_storage_bucket=tenant.byo_storage_bucket,
        byo_storage_public_url=tenant.byo_storage_public_url,
        byo_storage_region=tenant.byo_storage_region,
        has_access_key=bool(tenant.byo_storage_access_key),
        has_secret_key=bool(tenant.byo_storage_secret_key),
    )
