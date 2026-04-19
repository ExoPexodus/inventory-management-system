from __future__ import annotations

import pytest
from sqlalchemy.orm import Session
from uuid import uuid4

from app.auth.deps import OperatorContext
from app.models import PlatformOperator, PlatformTenant
from app.routers.tenants import (
    PatchTenantCurrencyBody,
    TenantCreate,
    TenantPatch,
    create_tenant,
    get_tenant_currency,
    patch_tenant,
    patch_tenant_currency,
)


def _ctx(operator: PlatformOperator) -> OperatorContext:
    return OperatorContext(operator_id=operator.id, email=operator.email)


def test_get_currency_returns_platform_values(db: Session, platform_tenant: PlatformTenant, platform_operator: PlatformOperator) -> None:
    platform_tenant.default_currency_code = "INR"
    platform_tenant.currency_exponent = 2
    platform_tenant.currency_symbol_override = "Rs"
    db.commit()

    result = get_tenant_currency(tenant_id=platform_tenant.id, ctx=_ctx(platform_operator), db=db)

    assert result.default_currency_code == "INR"
    assert result.currency_exponent == 2
    assert result.currency_symbol_override == "Rs"


def test_patch_currency_updates_all_fields(db: Session, platform_tenant: PlatformTenant, platform_operator: PlatformOperator) -> None:
    result = patch_tenant_currency(
        tenant_id=platform_tenant.id,
        body=PatchTenantCurrencyBody(
            default_currency_code="INR",
            currency_exponent=2,
            currency_symbol_override="Rs",
        ),
        ctx=_ctx(platform_operator),
        db=db,
    )
    db.refresh(platform_tenant)

    assert platform_tenant.default_currency_code == "INR"
    assert platform_tenant.currency_exponent == 2
    assert platform_tenant.currency_symbol_override == "Rs"
    assert result.default_currency_code == "INR"


def test_patch_currency_accepts_partial_update(db: Session, platform_tenant: PlatformTenant, platform_operator: PlatformOperator) -> None:
    platform_tenant.default_currency_code = "USD"
    platform_tenant.currency_exponent = 2
    db.commit()

    patch_tenant_currency(
        tenant_id=platform_tenant.id,
        body=PatchTenantCurrencyBody(default_currency_code="EUR"),
        ctx=_ctx(platform_operator),
        db=db,
    )
    db.refresh(platform_tenant)

    assert platform_tenant.default_currency_code == "EUR"
    assert platform_tenant.currency_exponent == 2


def test_patch_rejects_invalid_currency_code() -> None:
    with pytest.raises(Exception):
        PatchTenantCurrencyBody(default_currency_code="TOOLONG")


def test_patch_rejects_negative_exponent() -> None:
    with pytest.raises(Exception):
        PatchTenantCurrencyBody(currency_exponent=-1)


def test_create_tenant_accepts_currency_and_deployment_mode(
    db: Session, platform_operator,
) -> None:
    result = create_tenant(
        body=TenantCreate(
            name="New Tenant",
            slug=f"new-{uuid4().hex[:8]}",
            region="in",
            api_base_url="http://new.local",
            default_currency_code="INR",
            currency_exponent=2,
            currency_symbol_override="Rs",
            deployment_mode="on_prem",
        ),
        ctx=_ctx(platform_operator),
        db=db,
    )
    tenant = db.get(PlatformTenant, result.id)
    assert tenant.default_currency_code == "INR"
    assert tenant.deployment_mode == "on_prem"


def test_create_tenant_defaults_currency_to_usd_and_mode_to_cloud(
    db: Session, platform_operator,
) -> None:
    result = create_tenant(
        body=TenantCreate(
            name="Defaulted",
            slug=f"def-{uuid4().hex[:8]}",
            region="in",
            api_base_url="http://def.local",
        ),
        ctx=_ctx(platform_operator),
        db=db,
    )
    tenant = db.get(PlatformTenant, result.id)
    assert tenant.default_currency_code == "USD"
    assert tenant.currency_exponent == 2
    assert tenant.deployment_mode == "cloud"


def test_patch_tenant_accepts_deployment_mode(
    db: Session, platform_tenant: PlatformTenant, platform_operator,
) -> None:
    patch_tenant(
        tenant_id=platform_tenant.id,
        body=TenantPatch(deployment_mode="on_prem"),
        ctx=_ctx(platform_operator),
        db=db,
    )
    db.refresh(platform_tenant)
    assert platform_tenant.deployment_mode == "on_prem"


def test_patch_tenant_rejects_invalid_deployment_mode() -> None:
    with pytest.raises(Exception):
        TenantPatch(deployment_mode="invalid_mode")
