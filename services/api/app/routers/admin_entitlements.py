"""Admin endpoints for managing entitlements: per-tenant feature overrides + engineering flags.

Auth: requires ``entitlements:manage`` permission. The migration deliberately
does NOT auto-grant this to any role — it is IMS-staff-only and must be granted
to specific operators by a separate workflow (or directly via SQL during
incident response). The admin web should hide this UI behind a separate
feature gate / role check.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.billing.entitlements import invalidate_cache
from app.billing.features import get_definition
from app.db.admin_deps_db import get_db_admin
from app.models import TenantFeatureOverride

router = APIRouter(
    prefix="/v1/admin/entitlements",
    tags=["Admin Entitlements"],
    dependencies=[require_permission("entitlements:manage")],
)


# --- Schemas ---

class TenantFeatureOverrideIn(BaseModel):
    feature_key: str = Field(min_length=1, max_length=128)
    value: Any
    reason: str | None = None
    expires_at: datetime | None = None


class TenantFeatureOverrideOut(BaseModel):
    id: UUID
    tenant_id: UUID
    feature_key: str
    value: Any
    reason: str | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FeatureFlagOut(BaseModel):
    id: UUID
    key: str
    default_state: bool
    rollout_rules: dict | None
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Routes ---

def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator not assigned to a tenant",
        )
    return ctx.tenant_id


@router.get("/overrides", response_model=list[TenantFeatureOverrideOut])
def list_overrides(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[TenantFeatureOverride]:
    tenant_id = _require_tenant(ctx)
    rows = db.execute(
        select(TenantFeatureOverride).where(TenantFeatureOverride.tenant_id == tenant_id)
    ).scalars().all()
    return list(rows)


@router.post("/overrides", response_model=TenantFeatureOverrideOut, status_code=status.HTTP_201_CREATED)
def create_override(
    body: TenantFeatureOverrideIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> TenantFeatureOverride:
    tenant_id = _require_tenant(ctx)

    if get_definition(body.feature_key) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown feature key: {body.feature_key}",
        )

    # Upsert: replace any existing override on the same key
    existing = db.execute(
        select(TenantFeatureOverride).where(
            TenantFeatureOverride.tenant_id == tenant_id,
            TenantFeatureOverride.feature_key == body.feature_key,
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.value = body.value
        existing.reason = body.reason
        existing.expires_at = body.expires_at
        existing.updated_at = datetime.now(UTC)
        row = existing
    else:
        row = TenantFeatureOverride(
            tenant_id=tenant_id,
            feature_key=body.feature_key,
            value=body.value,
            reason=body.reason,
            expires_at=body.expires_at,
        )
        db.add(row)

    db.commit()
    db.refresh(row)
    invalidate_cache(tenant_id)
    return row


@router.delete("/overrides/{override_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_override(
    override_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    row = db.get(TenantFeatureOverride, override_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Override not found")
    db.delete(row)
    db.commit()
    invalidate_cache(tenant_id)


# === Engineering flags ===

from app.billing.flags import invalidate_flag_cache
from app.models import FeatureFlag


class FeatureFlagIn(BaseModel):
    key: str = Field(min_length=1, max_length=128)
    default_state: bool = False
    rollout_rules: dict | None = None
    description: str | None = None


class FeatureFlagPatch(BaseModel):
    default_state: bool | None = None
    rollout_rules: dict | None = None
    description: str | None = None


# NOTE: FeatureFlagOut is already defined earlier in this file from Task 7 —
# do NOT redefine it here. Adding it would shadow the original.


@router.get("/flags", response_model=list[FeatureFlagOut])
def list_flags(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[FeatureFlag]:
    rows = db.execute(select(FeatureFlag)).scalars().all()
    return list(rows)


@router.post("/flags", response_model=FeatureFlagOut, status_code=status.HTTP_201_CREATED)
def create_flag(
    body: FeatureFlagIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> FeatureFlag:
    existing = db.execute(
        select(FeatureFlag).where(FeatureFlag.key == body.key)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Flag with key {body.key!r} already exists",
        )
    row = FeatureFlag(
        key=body.key,
        default_state=body.default_state,
        rollout_rules=body.rollout_rules,
        description=body.description,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    invalidate_flag_cache(body.key)
    return row


@router.patch("/flags/{flag_id}", response_model=FeatureFlagOut)
def update_flag(
    flag_id: UUID,
    body: FeatureFlagPatch,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> FeatureFlag:
    row = db.get(FeatureFlag, flag_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flag not found")

    if body.default_state is not None:
        row.default_state = body.default_state
    if body.rollout_rules is not None:
        row.rollout_rules = body.rollout_rules
    if body.description is not None:
        row.description = body.description

    db.commit()
    db.refresh(row)
    invalidate_flag_cache(row.key)
    return row


@router.delete("/flags/{flag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_flag(
    flag_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    row = db.get(FeatureFlag, flag_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flag not found")
    key = row.key
    db.delete(row)
    db.commit()
    invalidate_flag_cache(key)
