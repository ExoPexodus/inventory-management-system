# NOTE: `from __future__ import annotations` deliberately absent.
#
# Covers: clone and reassign-and-delete endpoints (basic CRUD already covered elsewhere).

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Permission, Role, RolePermission, Tenant, User


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None,
        tenant_id=tenant.id,
        role="owner",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset({"roles:read", "roles:write"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


@pytest.fixture()
def custom_role(db, tenant: Tenant) -> Role:
    """A plain custom role (no permissions, no users)."""
    role = Role(
        tenant_id=tenant.id,
        name=f"testrole_{uuid.uuid4().hex[:6]}",
        display_name="Test Role",
        is_system=False,
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


@pytest.fixture()
def target_role(db, tenant: Tenant) -> Role:
    """A second custom role, used as a re-assignment target."""
    role = Role(
        tenant_id=tenant.id,
        name=f"targetrole_{uuid.uuid4().hex[:6]}",
        display_name="Target Role",
        is_system=False,
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


# ---------------------------------------------------------------------------
# Clone
# ---------------------------------------------------------------------------


def test_clone_role_creates_copy(db, tenant: Tenant, auth_headers, custom_role: Role) -> None:
    client = TestClient(app)
    resp = client.post(f"/v1/admin/roles/{custom_role.id}/clone", headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "copy" in body["name"]
    assert body["id"] != str(custom_role.id)
    assert body["is_system"] is False


def test_clone_nonexistent_role_returns_404(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post(f"/v1/admin/roles/{uuid.uuid4()}/clone", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Reassign-and-delete
# ---------------------------------------------------------------------------


def test_reassign_and_delete_no_users(db, tenant: Tenant, auth_headers, custom_role: Role) -> None:
    """Role with no assigned users can be deleted with empty assignments list."""
    client = TestClient(app)
    resp = client.post(
        f"/v1/admin/roles/{custom_role.id}/reassign-and-delete",
        json={"assignments": []},
        headers=auth_headers,
    )
    assert resp.status_code == 204


def test_reassign_and_delete_with_users(
    db, tenant: Tenant, auth_headers, custom_role: Role, target_role: Role
) -> None:
    """Users currently on the role must be reassigned to another role before deletion."""
    user = User(
        tenant_id=tenant.id,
        role_id=custom_role.id,
        email=f"u-{uuid.uuid4().hex[:6]}@test.local",
        name="Test User",
        password_hash="x",
    )
    db.add(user)
    db.commit()

    client = TestClient(app)
    resp = client.post(
        f"/v1/admin/roles/{custom_role.id}/reassign-and-delete",
        json={
            "assignments": [
                {"user_id": str(user.id), "new_role_id": str(target_role.id)}
            ]
        },
        headers=auth_headers,
    )
    assert resp.status_code == 204

    # user should now point to target_role
    db.refresh(user)
    assert user.role_id == target_role.id


def test_reassign_and_delete_missing_user_assignment_rejected(
    db, tenant: Tenant, auth_headers, custom_role: Role
) -> None:
    """If a user holds the role but is NOT in assignments, return 422."""
    user = User(
        tenant_id=tenant.id,
        role_id=custom_role.id,
        email=f"u2-{uuid.uuid4().hex[:6]}@test.local",
        name="User Two",
        password_hash="x",
    )
    db.add(user)
    db.commit()

    client = TestClient(app)
    resp = client.post(
        f"/v1/admin/roles/{custom_role.id}/reassign-and-delete",
        json={"assignments": []},  # empty — missing the user
        headers=auth_headers,
    )
    assert resp.status_code == 422
