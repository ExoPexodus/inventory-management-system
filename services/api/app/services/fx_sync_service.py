"""Fetch live FX rates from frankfurter.app (ECB data, no API key required).

Called by the admin sync endpoint. Upserts rates into fx_rates with
source="frankfurter". Rates are fetched in one round-trip per base currency.

frankfurter.app is backed by the European Central Bank. Rates update daily
on business days. Supported currencies: ~30 majors (EUR, USD, GBP, INR, JPY,
AUD, CAD, CHF, CNY, SGD, AED, MYR, THB, HKD, SEK, NOK, DKK, NZD, ZAR, …).
"""
from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.billing.fx import set_rate

logger = logging.getLogger(__name__)

_FRANKFURTER_URL = "https://api.frankfurter.app/latest"

# All currencies frankfurter.app supports.
SUPPORTED_CURRENCIES = {
    "AUD", "BGN", "BRL", "CAD", "CHF", "CNY", "CZK", "DKK", "EUR",
    "GBP", "HKD", "HUF", "IDR", "ILS", "INR", "ISK", "JPY", "KRW",
    "MXN", "MYR", "NOK", "NZD", "PHP", "PLN", "RON", "SEK", "SGD",
    "THB", "TRY", "USD", "ZAR",
}


def sync_rates(
    db: Session,
    tenant_id: UUID,
    base: str,
    targets: list[str],
) -> dict[str, str]:
    """Fetch rates for base → each target and upsert into fx_rates.

    Returns a dict of {currency: rate_string} for what was stored.
    Raises httpx.HTTPError on network failure (caller decides how to surface it).
    """
    base = base.upper()
    targets = [t.upper() for t in targets if t.upper() != base]
    if not targets:
        return {}

    # Filter to currencies frankfurter actually supports
    supported_targets = [t for t in targets if t in SUPPORTED_CURRENCIES]
    unsupported = set(targets) - set(supported_targets)
    if unsupported:
        logger.warning("frankfurter.app does not support: %s", ", ".join(sorted(unsupported)))

    if not supported_targets:
        return {}

    resp = httpx.get(
        _FRANKFURTER_URL,
        params={"from": base, "to": ",".join(supported_targets)},
        timeout=10.0,
    )
    resp.raise_for_status()
    data = resp.json()

    rates_fetched: dict[str, str] = {}
    for currency, rate_val in data.get("rates", {}).items():
        rate = Decimal(str(rate_val))
        row = set_rate(db, tenant_id, base, currency, rate)
        row.source = "frankfurter"
        rates_fetched[currency] = str(rate)

    db.commit()
    logger.info(
        "Synced %d FX rates for tenant %s (base=%s, date=%s)",
        len(rates_fetched), tenant_id, base, data.get("date"),
    )
    return rates_fetched
