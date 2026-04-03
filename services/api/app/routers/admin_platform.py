"""Admin platform — tenant-level settings (currency, etc.)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep
from app.db.admin_deps_db import get_db_admin
from app.models import Tenant

router = APIRouter(prefix="/v1/admin", tags=["Admin Platform"])

SUPPORTED_CURRENCIES = {
    "USD": {"symbol": "$", "exponent": 2, "name": "US Dollar"},
    "INR": {"symbol": "₹", "exponent": 2, "name": "Indian Rupee"},
    "IDR": {"symbol": "Rp", "exponent": 0, "name": "Indonesian Rupiah"},
}


def _require_tenant(ctx):
    if ctx.is_legacy_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Legacy token not allowed here",
        )
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator not assigned to a tenant",
        )
    return ctx.tenant_id


# ---------------------------------------------------------------------------
# Currency settings
# ---------------------------------------------------------------------------


class CurrencySettingsOut(BaseModel):
    currency_code: str
    currency_symbol: str
    currency_exponent: int
    display_mode: Literal["symbol", "convert"]
    conversion_rate: float | None
    supported_currencies: list[dict]


class PatchCurrencyBody(BaseModel):
    currency_code: str | None = Field(default=None)
    display_mode: Literal["symbol", "convert"] | None = Field(default=None)
    conversion_rate: float | None = Field(default=None, ge=0)


@router.get("/tenant-settings/currency", response_model=CurrencySettingsOut)
def get_currency_settings(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> CurrencySettingsOut:
    tenant_id = _require_tenant(ctx)
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    code = tenant.default_currency_code or "USD"
    meta = SUPPORTED_CURRENCIES.get(code, SUPPORTED_CURRENCIES["USD"])
    symbol = tenant.currency_symbol_override or meta["symbol"]

    return CurrencySettingsOut(
        currency_code=code,
        currency_symbol=symbol,
        currency_exponent=tenant.currency_exponent,
        display_mode=tenant.currency_display_mode or "symbol",
        conversion_rate=tenant.currency_conversion_rate,
        supported_currencies=[
            {"code": k, "symbol": v["symbol"], "name": v["name"], "exponent": v["exponent"]}
            for k, v in SUPPORTED_CURRENCIES.items()
        ],
    )


@router.patch("/tenant-settings/currency", response_model=CurrencySettingsOut)
def patch_currency_settings(
    body: PatchCurrencyBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> CurrencySettingsOut:
    tenant_id = _require_tenant(ctx)
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    if body.currency_code is not None:
        if body.currency_code not in SUPPORTED_CURRENCIES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported currency. Must be one of: {', '.join(SUPPORTED_CURRENCIES)}",
            )
        meta = SUPPORTED_CURRENCIES[body.currency_code]
        tenant.default_currency_code = body.currency_code
        tenant.currency_exponent = meta["exponent"]
        tenant.currency_symbol_override = meta["symbol"]

    if body.display_mode is not None:
        tenant.currency_display_mode = body.display_mode

    if body.conversion_rate is not None:
        if body.display_mode == "symbol" and (tenant.currency_display_mode == "symbol"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="conversion_rate only applies when display_mode is 'convert'",
            )
        tenant.currency_conversion_rate = body.conversion_rate

    db.commit()
    db.refresh(tenant)

    code = tenant.default_currency_code or "USD"
    meta = SUPPORTED_CURRENCIES.get(code, SUPPORTED_CURRENCIES["USD"])
    return CurrencySettingsOut(
        currency_code=code,
        currency_symbol=tenant.currency_symbol_override or meta["symbol"],
        currency_exponent=tenant.currency_exponent,
        display_mode=tenant.currency_display_mode or "symbol",
        conversion_rate=tenant.currency_conversion_rate,
        supported_currencies=[
            {"code": k, "symbol": v["symbol"], "name": v["name"], "exponent": v["exponent"]}
            for k, v in SUPPORTED_CURRENCIES.items()
        ],
    )
