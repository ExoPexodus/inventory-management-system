"""Admin endpoint for getting presigned upload URLs for direct browser-to-R2 uploads."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Tenant
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


class PresignOut(BaseModel):
    upload_url: str
    public_url: str
    key: str
    expires_in: int
    content_type: str


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Operator not assigned to a tenant")
    return ctx.tenant_id


@router.post("/presign-upload", response_model=PresignOut)
def get_presign_upload_url(
    body: PresignIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> PresignOut:
    """Get a presigned PUT URL for uploading an image directly to R2.

    Flow:
      1. Call this endpoint → get { upload_url, public_url }
      2. PUT file bytes to upload_url from the browser (no auth needed for the PUT)
      3. Save public_url as the image URL on the product
    """
    tenant_id = _require_tenant(ctx)
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    try:
        result = presign_upload(
            tenant=tenant,
            folder=body.folder.strip("/"),
            filename=body.filename,
            content_type=body.content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return PresignOut(**result)
