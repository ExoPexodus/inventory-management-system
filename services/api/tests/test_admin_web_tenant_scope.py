from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.auth.admin_deps import AdminContext
from app.routers.admin_web import _coerce_tenant_scope, _require_operator_tenant


def _ctx(*, tenant_id=None, legacy=False) -> AdminContext:
    return AdminContext(
        user_id=uuid4(),
        tenant_id=tenant_id,
        role="admin",
        role_id=None,
        is_legacy_token=legacy,
    )


def test_require_operator_tenant_rejects_legacy() -> None:
    with pytest.raises(HTTPException) as exc:
        _require_operator_tenant(_ctx(tenant_id=uuid4(), legacy=True))
    assert exc.value.status_code == 403


def test_require_operator_tenant_rejects_unassigned_operator() -> None:
    with pytest.raises(HTTPException) as exc:
        _require_operator_tenant(_ctx(tenant_id=None))
    assert exc.value.status_code == 403


def test_coerce_tenant_scope_rejects_cross_tenant_request() -> None:
    tenant_a = uuid4()
    tenant_b = uuid4()
    with pytest.raises(HTTPException) as exc:
        _coerce_tenant_scope(_ctx(tenant_id=tenant_a), tenant_b)
    assert exc.value.status_code == 403


def test_coerce_tenant_scope_uses_operator_tenant_when_unspecified() -> None:
    tenant = uuid4()
    out = _coerce_tenant_scope(_ctx(tenant_id=tenant), None)
    assert out == tenant
