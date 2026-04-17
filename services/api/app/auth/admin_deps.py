from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import decode_token
from app.config import settings
from app.db.session import get_db
from app.models import User
from app.services.permission_service import get_role_permissions


@dataclass(frozen=True)
class AdminContext:
    user_id: UUID | None
    tenant_id: UUID | None
    role: str | None
    role_id: UUID | None
    is_legacy_token: bool
    permissions: frozenset[str] = field(default_factory=frozenset)

    # Backwards-compat alias — some routers still reference `operator_id`
    @property
    def operator_id(self) -> UUID | None:
        return self.user_id


def _verify_legacy_admin_token(x_admin_token: str | None) -> bool:
    expected = settings.admin_api_token
    if not expected:
        return False
    return bool(x_admin_token and x_admin_token == expected)


def require_admin_context(
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> AdminContext:
    """Accepts static X-Admin-Token (legacy) or Bearer JWT from POST /v1/admin/auth/login."""
    if _verify_legacy_admin_token(x_admin_token):
        return AdminContext(
            user_id=None,
            tenant_id=None,
            role=None,
            role_id=None,
            is_legacy_token=True,
            permissions=frozenset(),
        )

    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization[7:].strip()
        try:
            payload = decode_token(raw)
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer token",
            ) from None
        # Accept both legacy "operator" type (existing admin-web JWTs)
        # and the new "user" type (issued after merge)
        if payload.get("typ") not in ("operator", "user"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Wrong token type",
            )
        sub = payload.get("sub")
        try:
            user_id = UUID(str(sub))
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Malformed user subject",
            ) from None
        user = db.execute(
            select(User).where(User.id == user_id, User.is_active.is_(True))
        ).scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User no longer active",
            )

        role_name = user.role.name if user.role else None
        permissions: frozenset[str] = frozenset()
        if user.role_id is not None:
            permissions = get_role_permissions(db, user.role_id)

        return AdminContext(
            user_id=user.id,
            tenant_id=user.tenant_id,
            role=role_name,
            role_id=user.role_id,
            is_legacy_token=False,
            permissions=permissions,
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing admin credentials (X-Admin-Token or Authorization: Bearer)",
    )


AdminAuthDep = Annotated[AdminContext, Depends(require_admin_context)]
# Backward-compatible name for routers importing AdminTokenDep
AdminTokenDep = AdminAuthDep


def require_permission(*codenames: str):
    """FastAPI dependency factory that enforces at least one of the given codenames.

    Legacy token (X-Admin-Token) bypasses all checks.
    Usage:
        ctx: Annotated[AdminContext, Depends(require_permission("staff:read"))]
    """

    def _dep(ctx: AdminAuthDep) -> AdminContext:
        if ctx.is_legacy_token:
            return ctx
        if not codenames:
            return ctx
        if not ctx.permissions.intersection(codenames):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {' or '.join(codenames)}",
            )
        return ctx

    return Depends(_dep)


def require_admin_web_access():
    """Enforces admin_web:access permission for endpoints that should only be used by the admin web portal."""
    return require_permission("admin_web:access")


def require_admin_mobile_access():
    """Enforces admin_mobile:access permission."""
    return require_permission("admin_mobile:access")
