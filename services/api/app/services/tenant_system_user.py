"""Seed and fetch the per-tenant system user used for automated action attribution."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Role, User

SYSTEM_ROLE_NAME = "system"
SYSTEM_USER_EMAIL_TEMPLATE = "system+{tenant_id}@internal.ims"


def _get_system_role(db: Session, tenant_id: uuid.UUID) -> Optional[Role]:
    return db.execute(
        select(Role).where(Role.tenant_id == tenant_id, Role.name == SYSTEM_ROLE_NAME)
    ).scalar_one_or_none()


def get_tenant_system_user(db: Session, tenant_id: uuid.UUID) -> Optional[User]:
    role = _get_system_role(db, tenant_id)
    if role is None:
        return None
    return db.execute(
        select(User).where(User.tenant_id == tenant_id, User.role_id == role.id)
    ).scalar_one_or_none()


def seed_tenant_system_user(db: Session, tenant_id: uuid.UUID) -> User:
    """Idempotently create the system role and system user for a tenant."""
    role = _get_system_role(db, tenant_id)
    if role is None:
        role = Role(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=SYSTEM_ROLE_NAME,
            display_name="System (automated actions)",
            is_system=True,
        )
        db.add(role)
        db.flush()

    email = SYSTEM_USER_EMAIL_TEMPLATE.format(tenant_id=tenant_id)
    existing = db.execute(
        select(User).where(User.tenant_id == tenant_id, User.email == email)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    user = User(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        role_id=role.id,
        email=email,
        name="System",
        password_hash=None,
        is_active=False,
    )
    db.add(user)
    db.flush()
    return user
