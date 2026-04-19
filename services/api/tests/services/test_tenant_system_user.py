from __future__ import annotations

import uuid
from sqlalchemy.orm import Session

from app.models import Role, Tenant, User
from app.services.tenant_system_user import (
    SYSTEM_ROLE_NAME,
    get_tenant_system_user,
    seed_tenant_system_user,
)


def test_seed_creates_system_role_and_user(db: Session, tenant: Tenant) -> None:
    user = seed_tenant_system_user(db, tenant.id)
    db.commit()

    assert user.email.startswith("system+")
    assert user.email.endswith("@internal.ims")
    assert user.is_active is False
    assert user.password_hash is None
    role = db.get(Role, user.role_id)
    assert role is not None
    assert role.name == SYSTEM_ROLE_NAME
    assert role.is_system is True


def test_seed_is_idempotent(db: Session, tenant: Tenant) -> None:
    first = seed_tenant_system_user(db, tenant.id)
    db.commit()
    second = seed_tenant_system_user(db, tenant.id)
    db.commit()

    assert first.id == second.id


def test_get_tenant_system_user_returns_seeded_user(db: Session, tenant: Tenant) -> None:
    seeded = seed_tenant_system_user(db, tenant.id)
    db.commit()
    fetched = get_tenant_system_user(db, tenant.id)
    assert fetched is not None
    assert fetched.id == seeded.id


def test_get_tenant_system_user_returns_none_if_not_seeded(db: Session) -> None:
    missing_tenant = uuid.uuid4()
    assert get_tenant_system_user(db, missing_tenant) is None
