"""APK release management endpoints — upload, list, update, deactivate."""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.deps import OperatorDep
from app.db.session import get_db
from app.models.tables import AppRelease
from app.services.audit_service import write_audit
from app.services.storage_service import save_upload

router = APIRouter(prefix="/v1/platform/releases", tags=["Platform Releases"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ReleaseOut(BaseModel):
    id: UUID
    app_name: str
    version: str
    version_code: int
    changelog: str | None
    file_size_bytes: int | None
    checksum_sha256: str | None
    is_active: bool
    created_at: datetime


class ReleasePatch(BaseModel):
    changelog: str | None = None
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# List releases
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ReleaseOut])
def list_releases(
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
    app_name: str | None = None,
    active_only: bool = True,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ReleaseOut]:
    stmt = select(AppRelease).order_by(AppRelease.created_at.desc())
    if app_name:
        stmt = stmt.where(AppRelease.app_name == app_name)
    if active_only:
        stmt = stmt.where(AppRelease.is_active.is_(True))
    stmt = stmt.limit(limit)
    rows = db.execute(stmt).scalars().all()
    return [_to_out(r) for r in rows]


# ---------------------------------------------------------------------------
# Upload APK
# ---------------------------------------------------------------------------


@router.post("", response_model=ReleaseOut, status_code=status.HTTP_201_CREATED)
async def upload_release(
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
    app_name: str = Form(...),
    version: str = Form(...),
    version_code: int = Form(...),
    changelog: str = Form(default=""),
) -> ReleaseOut:
    if app_name not in ("cashier", "admin_mobile"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="app_name must be 'cashier' or 'admin_mobile'")

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    if len(file_bytes) > 200 * 1024 * 1024:  # 200MB limit
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File too large (max 200MB)")

    rel_path, size, sha = save_upload(file_bytes, app_name, version, file.filename or "upload.apk")

    release = AppRelease(
        id=_uuid.uuid4(),
        app_name=app_name,
        version=version,
        version_code=version_code,
        changelog=changelog or None,
        file_path=rel_path,
        file_size_bytes=size,
        checksum_sha256=sha,
        uploaded_by=ctx.operator_id,
    )
    db.add(release)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Version {version} already exists for {app_name}")

    write_audit(db, operator_id=ctx.operator_id, action="upload_release", resource_type="app_release", resource_id=str(release.id), details={"app_name": app_name, "version": version})
    db.commit()
    db.refresh(release)
    return _to_out(release)


# ---------------------------------------------------------------------------
# Update / deactivate
# ---------------------------------------------------------------------------


@router.patch("/{release_id}", response_model=ReleaseOut)
def patch_release(
    release_id: UUID,
    body: ReleasePatch,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> ReleaseOut:
    release = db.get(AppRelease, release_id)
    if release is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Release not found")

    patch = body.model_dump(exclude_unset=True)
    for key, val in patch.items():
        setattr(release, key, val)

    write_audit(db, operator_id=ctx.operator_id, action="update_release", resource_type="app_release", resource_id=str(release_id), details=patch)
    db.commit()
    db.refresh(release)
    return _to_out(release)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_out(r: AppRelease) -> ReleaseOut:
    return ReleaseOut(
        id=r.id,
        app_name=r.app_name,
        version=r.version,
        version_code=r.version_code,
        changelog=r.changelog,
        file_size_bytes=r.file_size_bytes,
        checksum_sha256=r.checksum_sha256,
        is_active=r.is_active,
        created_at=r.created_at,
    )
