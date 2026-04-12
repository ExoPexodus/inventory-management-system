"""Role and permission management endpoints for admin operators."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, AdminContext, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import AdminUser, Permission, Role, RolePermission
from app.services.permission_service import invalidate_role_cache

router = APIRouter(prefix="/v1/admin/roles", tags=["Admin Roles"])


def _require_operator_tenant(ctx: AdminContext) -> UUID:
    if ctx.is_legacy_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Legacy admin token is not allowed for this endpoint",
        )
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator is not assigned to a tenant",
        )
    return ctx.tenant_id


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------

class PermissionOut(BaseModel):
    id: UUID
    codename: str
    display_name: str
    category: str
    description: str | None = None


class RoleOut(BaseModel):
    id: UUID
    tenant_id: UUID | None
    name: str
    display_name: str
    is_system: bool
    permissions: list[str]  # codenames


class CreateRoleBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    permissions: list[str] = Field(default_factory=list)


class UpdateRoleBody(BaseModel):
    display_name: str | None = Field(default=None, max_length=128)
    permissions: list[str] | None = None  # None means don't change


def _role_out(role: Role, db: Session) -> RoleOut:
    codenames = [rp.permission.codename for rp in role.permissions if rp.permission]
    return RoleOut(
        id=role.id,
        tenant_id=role.tenant_id,
        name=role.name,
        display_name=role.display_name,
        is_system=role.is_system,
        permissions=sorted(codenames),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/permissions", response_model=list[PermissionOut], dependencies=[require_permission("roles:read")])
def list_permissions(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[PermissionOut]:
    """List all available permission codenames (for role-builder UI)."""
    _require_operator_tenant(ctx)
    rows = db.execute(select(Permission).order_by(Permission.category, Permission.codename)).scalars().all()
    return [
        PermissionOut(id=r.id, codename=r.codename, display_name=r.display_name, category=r.category, description=r.description)
        for r in rows
    ]


@router.get("", response_model=list[RoleOut], dependencies=[require_permission("roles:read")])
def list_roles(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[RoleOut]:
    """List all roles for this tenant (system + custom) with their permission codenames."""
    tenant_id = _require_operator_tenant(ctx)
    roles = (
        db.execute(
            select(Role)
            .where(Role.tenant_id == tenant_id)
            .order_by(Role.is_system.desc(), Role.name)
        )
        .scalars()
        .all()
    )
    # eager load permissions
    for role in roles:
        _ = role.permissions  # trigger lazy load within session
    return [_role_out(role, db) for role in roles]


@router.post("", response_model=RoleOut, status_code=201, dependencies=[require_permission("roles:write")])
def create_role(
    body: CreateRoleBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> RoleOut:
    """Create a custom role with selected permission codenames."""
    tenant_id = _require_operator_tenant(ctx)

    # Validate permission codenames
    perm_rows = db.execute(
        select(Permission).where(Permission.codename.in_(body.permissions))
    ).scalars().all()
    found_codenames = {p.codename for p in perm_rows}
    unknown = set(body.permissions) - found_codenames
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown permission codenames: {sorted(unknown)}",
        )

    role = Role(
        tenant_id=tenant_id,
        name=body.name.strip().lower().replace(" ", "_"),
        display_name=body.display_name.strip(),
        is_system=False,
    )
    db.add(role)
    db.flush()

    for perm in perm_rows:
        db.add(RolePermission(role_id=role.id, permission_id=perm.id))

    db.commit()
    db.refresh(role)
    return _role_out(role, db)


@router.patch("/{role_id}", response_model=RoleOut, dependencies=[require_permission("roles:write")])
def update_role(
    role_id: UUID,
    body: UpdateRoleBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> RoleOut:
    """Update a role's display name and/or permissions."""
    tenant_id = _require_operator_tenant(ctx)
    role = db.execute(
        select(Role).where(Role.id == role_id, Role.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    if body.display_name is not None:
        role.display_name = body.display_name.strip()

    if body.permissions is not None:
        perm_rows = db.execute(
            select(Permission).where(Permission.codename.in_(body.permissions))
        ).scalars().all()
        found_codenames = {p.codename for p in perm_rows}
        unknown = set(body.permissions) - found_codenames
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unknown permission codenames: {sorted(unknown)}",
            )
        # Replace all permissions
        db.execute(
            RolePermission.__table__.delete().where(RolePermission.role_id == role_id)
        )
        db.flush()
        for perm in perm_rows:
            db.add(RolePermission(role_id=role.id, permission_id=perm.id))

    db.commit()
    db.refresh(role)
    invalidate_role_cache(role_id)
    return _role_out(role, db)


@router.delete("/{role_id}", status_code=204, dependencies=[require_permission("roles:write")])
def delete_role(
    role_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    """Delete a custom role. System roles (is_system=True) cannot be deleted."""
    tenant_id = _require_operator_tenant(ctx)
    role = db.execute(
        select(Role).where(Role.id == role_id, Role.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System roles cannot be deleted",
        )
    # Check for operators assigned to this role
    assigned_count = db.execute(
        select(func.count()).select_from(AdminUser).where(AdminUser.role_id == role_id)
    ).scalar_one()
    if assigned_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete role: {assigned_count} operator(s) are assigned to it. Reassign them first.",
        )
    db.delete(role)
    db.commit()
    invalidate_role_cache(role_id)
