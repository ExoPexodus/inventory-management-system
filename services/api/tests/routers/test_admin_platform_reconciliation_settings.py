from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminContext
from app.models import Tenant
from app.routers.admin_platform import (
    PatchReconciliationBody,
    get_reconciliation_settings,
    patch_reconciliation_settings,
)


def _ctx(tenant_id):
    return AdminContext(
        user_id=None,
        tenant_id=tenant_id,
        role="admin",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset(),
    )


def test_get_reconciliation_settings_returns_tenant_values(
    db: Session, tenant: Tenant,
) -> None:
    tenant.auto_resolve_shortage_cents = 3000
    tenant.auto_resolve_overage_cents = 7000
    db.commit()

    result = get_reconciliation_settings(ctx=_ctx(tenant.id), db=db)

    assert result.auto_resolve_shortage_cents == 3000
    assert result.auto_resolve_overage_cents == 7000


def test_patch_updates_both_fields(db: Session, tenant: Tenant) -> None:
    patch_reconciliation_settings(
        body=PatchReconciliationBody(
            auto_resolve_shortage_cents=1500,
            auto_resolve_overage_cents=2500,
        ),
        ctx=_ctx(tenant.id),
        db=db,
    )
    db.refresh(tenant)
    assert tenant.auto_resolve_shortage_cents == 1500
    assert tenant.auto_resolve_overage_cents == 2500


def test_patch_accepts_partial_update(db: Session, tenant: Tenant) -> None:
    tenant.auto_resolve_shortage_cents = 1000
    tenant.auto_resolve_overage_cents = 2000
    db.commit()

    patch_reconciliation_settings(
        body=PatchReconciliationBody(auto_resolve_shortage_cents=5000),
        ctx=_ctx(tenant.id),
        db=db,
    )
    db.refresh(tenant)
    assert tenant.auto_resolve_shortage_cents == 5000
    assert tenant.auto_resolve_overage_cents == 2000


def test_patch_rejects_negative_values() -> None:
    with pytest.raises(Exception):  # Pydantic validation error
        PatchReconciliationBody(auto_resolve_shortage_cents=-1)
