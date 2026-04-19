from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.auth.deps import OperatorContext
from app.models import PlatformOperator, PlatformTenant
from app.routers.tenants import (
    PatchTenantCurrencyBody,
    get_tenant_currency,
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
