"""Unified auth endpoints — PIN login and PIN management for mobile quick-unlock."""

from __future__ import annotations

import bcrypt
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep
from app.auth.deps import DeviceAuth, get_device_auth
from app.auth.jwt import create_operator_access_token
from app.db.session import get_db
from app.models import Tenant, User
from app.services.permission_service import get_role_permissions

router = APIRouter(prefix="/v1/auth", tags=["Unified Auth"])


class PinLoginBody(BaseModel):
    pin: str = Field(min_length=4, max_length=16)


class PinLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    tenant_id: UUID
    tenant_slug: str
    role: str | None
    permissions: list[str]
    user_id: UUID
    name: str


@router.post("/pin-login", response_model=PinLoginResponse)
def pin_login(
    body: PinLoginBody,
    auth: Annotated[DeviceAuth, Depends(get_device_auth)],
    db: Annotated[Session, Depends(get_db)],
) -> PinLoginResponse:
    """Authenticate via PIN on an already-enrolled device (admin_mobile quick-unlock).

    Requires the device_id in the DeviceAuth token AND a matching user with pin_hash set.
    The user's role must grant admin_mobile:access.
    """
    user = db.execute(
        select(User).where(
            User.tenant_id == auth.tenant_id,
            User.device_id == auth.device_id,
            User.is_active.is_(True),
        )
    ).scalar_one_or_none()

    if user is None or user.pin_hash is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No PIN is set for this device. Log in with password first.",
        )

    try:
        ok = bcrypt.checkpw(body.pin.strip().encode(), user.pin_hash.encode("ascii"))
    except ValueError:
        ok = False
    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid PIN")

    # Enforce admin_mobile:access permission
    perms = get_role_permissions(db, user.role_id) if user.role_id else frozenset()
    if "admin_mobile:access" not in perms:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your role does not grant admin mobile access.",
        )

    tenant = db.get(Tenant, user.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant not found")

    access, ttl = create_operator_access_token(
        operator_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role.name if user.role else None,
    )

    return PinLoginResponse(
        access_token=access,
        expires_in=ttl,
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        role=user.role.name if user.role else None,
        permissions=sorted(perms),
        user_id=user.id,
        name=user.name,
    )


class SetPinBody(BaseModel):
    pin: str = Field(min_length=4, max_length=16)


@router.post("/set-pin", status_code=200)
def set_pin(
    body: SetPinBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    """Set or rotate the PIN for the currently-authenticated user (for mobile quick-unlock)."""
    if ctx.user_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No user session")
    if not body.pin.strip().isdigit():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="PIN must be numeric")

    user = db.get(User, ctx.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user.pin_hash = bcrypt.hashpw(body.pin.strip().encode(), bcrypt.gensalt()).decode("ascii")
    db.commit()
    return {"status": "ok"}


@router.post("/reset-pin", status_code=200)
def reset_pin(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    """Clear the PIN for the current user. Forces fall-back to password login."""
    if ctx.user_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No user session")
    user = db.get(User, ctx.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.pin_hash = None
    db.commit()
    return {"status": "ok"}
