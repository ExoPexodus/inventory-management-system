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
from app.models import AdminUser
from app.services.permission_service import get_role_permissions


@dataclass(frozen=True)
class AdminContext:
    operator_id: UUID | None
    tenant_id: UUID | None
    role: str | None
    role_id: UUID | None
    is_legacy_token: bool
    permissions: frozenset[str] = field(default_factory=frozenset)


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
            operator_id=None,
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
        if payload.get("typ") != "operator":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Wrong token type",
            )
        sub = payload.get("sub")
        try:
            operator_id = UUID(str(sub))
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Malformed operator subject",
            ) from None
        operator = db.execute(
            select(AdminUser).where(AdminUser.id == operator_id, AdminUser.is_active.is_(True))
        ).scalar_one_or_none()
        if operator is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Operator no longer active",
            )

        role_name = operator.role.name if operator.role else None
        permissions: frozenset[str] = frozenset()
        if operator.role_id is not None:
            permissions = get_role_permissions(db, operator.role_id)

        return AdminContext(
            operator_id=operator.id,
            tenant_id=operator.tenant_id,
            role=role_name,
            role_id=operator.role_id,
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
