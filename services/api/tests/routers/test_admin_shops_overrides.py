from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminContext
from app.models import Shop, Tenant
from app.routers.admin_shops import PatchShopBody, get_shop, patch_shop


def _ctx(tenant_id):
    return AdminContext(
        user_id=None,
        tenant_id=tenant_id,
        role="admin",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset(),
    )


def test_get_shop_returns_override_fields_nullable_by_default(
    db: Session, tenant: Tenant, shop: Shop,
) -> None:
    result = get_shop(shop_id=shop.id, ctx=_ctx(tenant.id), db=db)
    assert result.auto_resolve_shortage_cents_override is None
    assert result.auto_resolve_overage_cents_override is None


def test_patch_shop_sets_override(db: Session, tenant: Tenant, shop: Shop) -> None:
    patch_shop(
        shop_id=shop.id,
        body=PatchShopBody(auto_resolve_shortage_cents_override=2500),
        ctx=_ctx(tenant.id),
        db=db,
    )
    db.refresh(shop)
    assert shop.auto_resolve_shortage_cents_override == 2500


def test_patch_shop_clears_override_when_explicitly_sent_null(
    db: Session, tenant: Tenant, shop: Shop,
) -> None:
    shop.auto_resolve_shortage_cents_override = 2500
    db.commit()

    # Construct body by dumping JSON with explicit null so model_fields_set includes the key
    body = PatchShopBody.model_validate({"auto_resolve_shortage_cents_override": None})
    patch_shop(shop_id=shop.id, body=body, ctx=_ctx(tenant.id), db=db)
    db.refresh(shop)
    assert shop.auto_resolve_shortage_cents_override is None


def test_patch_shop_rejects_negative_override() -> None:
    with pytest.raises(Exception):
        PatchShopBody(auto_resolve_shortage_cents_override=-5)


def test_get_shop_404_for_unknown_id(db: Session, tenant: Tenant) -> None:
    with pytest.raises(HTTPException) as exc:
        get_shop(shop_id=uuid4(), ctx=_ctx(tenant.id), db=db)
    assert exc.value.status_code == 404


def test_get_shop_404_for_other_tenant(
    db: Session, tenant: Tenant, shop: Shop,
) -> None:
    other_tenant_id = uuid4()
    with pytest.raises(HTTPException) as exc:
        get_shop(shop_id=shop.id, ctx=_ctx(other_tenant_id), db=db)
    assert exc.value.status_code == 404
