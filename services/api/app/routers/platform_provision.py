"""Platform-initiated tenant provisioning endpoint.

Called by the platform service when a new tenant is created. Creates the tenant,
owner role (with all permissions), initial admin operator, and system user.
Idempotent — safe to call on an already-provisioned tenant.

Auth: X-Admin-Token (legacy global admin token).
"""
from __future__ import annotations

import uuid as _uuid
from typing import Annotated

import bcrypt
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.admin_deps_db import get_db_admin
from app.models import Permission, Role, RolePermission, Tenant, User
from app.services.tenant_system_user import seed_tenant_system_user

router = APIRouter(prefix="/v1/admin", tags=["Platform Provision"])

_OWNER_ROLE_NAME = "Owner"


def _require_admin_token(x_admin_token: str = Header(...)) -> None:
    if not settings.admin_api_token or x_admin_token != settings.admin_api_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token")


class InitialLicensePayload(BaseModel):
    subscription_status: str
    plan_codename: str
    billing_cycle: str | None = None
    max_shops: int = 1
    max_employees: int = 5
    storage_limit_mb: int = 500
    trial_ends_at: str | None = None
    current_period_end: str | None = None
    grace_period_days: int = 7


class ProvisionTenantBody(BaseModel):
    tenant_id: _uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=64)
    admin_email: EmailStr
    admin_password: str = Field(min_length=8)
    # Storage configuration — defaults to "platform" mode
    storage_mode: str = Field(default="platform", pattern="^(platform|byo)$")
    byo_storage_endpoint: str | None = None
    byo_storage_bucket: str | None = None
    byo_storage_access_key: str | None = None
    byo_storage_secret_key: str | None = None
    byo_storage_public_url: str | None = None
    byo_storage_region: str | None = Field(default="auto")
    # License seed — populated at provision time so new tenants have a cache row immediately
    initial_license: InitialLicensePayload | None = None


class ProvisionTenantOut(BaseModel):
    tenant_id: _uuid.UUID
    operator_id: _uuid.UUID | None
    tenant_status: str  # "created" | "existing"
    operator_status: str  # "created" | "existing"


@router.post(
    "/provision-tenant",
    response_model=ProvisionTenantOut,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(_require_admin_token)],
)
def provision_tenant(
    body: ProvisionTenantBody,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ProvisionTenantOut:
    # ── 1. Tenant ────────────────────────────────────────────────────────────
    tenant = db.get(Tenant, body.tenant_id)
    tenant_status = "existing"
    if tenant is None:
        # Also check by slug to avoid duplicate slugs with different IDs
        tenant = db.execute(
            select(Tenant).where(Tenant.slug == body.slug)
        ).scalar_one_or_none()
        if tenant is not None:
            # Slug already taken by a different UUID — conflict
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Tenant slug '{body.slug}' already exists with a different ID",
            )
        tenant = Tenant(id=body.tenant_id, name=body.name, slug=body.slug)
        db.add(tenant)
        # Apply storage configuration
        tenant.storage_mode = body.storage_mode
        if body.storage_mode == "byo":
            from app.services.email_service import encrypt_secret as _enc
            tenant.byo_storage_endpoint = body.byo_storage_endpoint
            tenant.byo_storage_bucket = body.byo_storage_bucket
            tenant.byo_storage_public_url = body.byo_storage_public_url
            tenant.byo_storage_region = body.byo_storage_region or "auto"
            if body.byo_storage_access_key:
                tenant.byo_storage_access_key = _enc(body.byo_storage_access_key)
            if body.byo_storage_secret_key:
                tenant.byo_storage_secret_key = _enc(body.byo_storage_secret_key)
        db.flush()
        tenant_status = "created"

    tenant_id = tenant.id

    # ── 2. Owner role ─────────────────────────────────────────────────────────
    owner_role = db.execute(
        select(Role).where(Role.tenant_id == tenant_id, Role.name == _OWNER_ROLE_NAME)
    ).scalar_one_or_none()

    if owner_role is None:
        owner_role = Role(
            id=_uuid.uuid4(),
            tenant_id=tenant_id,
            name=_OWNER_ROLE_NAME,
            display_name="Owner",
            is_system=False,
        )
        db.add(owner_role)
        db.flush()

        # Grant all existing permissions to the owner role
        all_perms = db.execute(select(Permission)).scalars().all()
        for perm in all_perms:
            db.add(RolePermission(
                id=_uuid.uuid4(),
                role_id=owner_role.id,
                permission_id=perm.id,
            ))
        db.flush()

    # ── 3. System user ───────────────────────────────────────────────────────
    seed_tenant_system_user(db, tenant_id)

    # ── 4. Initial admin operator ─────────────────────────────────────────────
    email = body.admin_email.strip().lower()
    existing_op = db.execute(
        select(User).where(User.tenant_id == tenant_id, User.email == email)
    ).scalar_one_or_none()

    operator_status = "existing"
    operator_id: _uuid.UUID | None = None

    if existing_op is not None:
        operator_id = existing_op.id
    else:
        pw_hash = bcrypt.hashpw(body.admin_password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
        op = User(
            id=_uuid.uuid4(),
            tenant_id=tenant_id,
            role_id=owner_role.id,
            email=email,
            name=email.split("@")[0],
            password_hash=pw_hash,
            is_active=True,
        )
        db.add(op)
        db.flush()
        operator_id = op.id
        operator_status = "created"

    if body.initial_license is not None and tenant_status == "created":
        from app.services.license_service import _upsert_cache
        _upsert_cache(db, tenant_id, body.initial_license.model_dump())

    db.commit()
    return ProvisionTenantOut(
        tenant_id=tenant_id,
        operator_id=operator_id,
        tenant_status=tenant_status,
        operator_status=operator_status,
    )
