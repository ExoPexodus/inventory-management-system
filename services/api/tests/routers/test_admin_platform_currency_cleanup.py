from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminContext
from app.models import Tenant
from app.routers.admin_platform import (
    PatchCurrencyBody,
    get_currency_settings,
    patch_currency_settings,
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


def test_get_currency_response_has_no_display_mode_or_conversion_rate(
    db: Session, tenant: Tenant,
) -> None:
    tenant.default_currency_code = "INR"
    tenant.currency_exponent = 2
    db.commit()

    result = get_currency_settings(ctx=_ctx(tenant.id), db=db)
    result_dict = result.model_dump()

    assert "display_mode" not in result_dict
    assert "conversion_rate" not in result_dict
    assert result_dict["currency_code"] == "INR"


def test_patch_currency_returns_410_gone(db: Session, tenant: Tenant) -> None:
    with pytest.raises(HTTPException) as exc:
        patch_currency_settings(
            body=PatchCurrencyBody(currency_code="USD"),
            ctx=_ctx(tenant.id),
            db=db,
        )
    assert exc.value.status_code == 410
    assert "platform" in exc.value.detail.lower() or "support" in exc.value.detail.lower()


def test_patch_body_rejects_display_mode() -> None:
    """PatchCurrencyBody should no longer accept display_mode or conversion_rate fields."""
    # When extra="forbid", passing these should raise. If model accepts extras silently,
    # at least assert the field is not in model_fields.
    assert "display_mode" not in PatchCurrencyBody.model_fields
    assert "conversion_rate" not in PatchCurrencyBody.model_fields
