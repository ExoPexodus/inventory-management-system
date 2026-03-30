from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.auth.admin_deps import AdminContext
from app.routers.admin import _require_operator_tenant as admin_require_operator_tenant
from app.routers.admin_web import _coerce_tenant_scope, _require_operator_tenant as web_require_operator_tenant


def _ctx(*, tenant_id=None, legacy=False) -> AdminContext:
    return AdminContext(
        operator_id=uuid4(),
        tenant_id=tenant_id,
        role="admin",
        is_legacy_token=legacy,
    )


def test_admin_require_operator_tenant_returns_operator_tenant() -> None:
    tenant = uuid4()
    assert admin_require_operator_tenant(_ctx(tenant_id=tenant)) == tenant


def test_admin_require_operator_tenant_rejects_legacy_token() -> None:
    with pytest.raises(HTTPException) as exc:
        admin_require_operator_tenant(_ctx(tenant_id=uuid4(), legacy=True))
    assert exc.value.status_code == 403


def test_admin_web_require_operator_tenant_returns_operator_tenant() -> None:
    tenant = uuid4()
    assert web_require_operator_tenant(_ctx(tenant_id=tenant)) == tenant


def test_admin_web_coerce_tenant_scope_accepts_matching_tenant() -> None:
    tenant = uuid4()
    assert _coerce_tenant_scope(_ctx(tenant_id=tenant), tenant) == tenant

