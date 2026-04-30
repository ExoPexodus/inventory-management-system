"""Timezone and financial-year helpers for multi-market localisation."""
from __future__ import annotations

from datetime import date, timedelta
from zoneinfo import available_timezones

FALLBACK_TZ = "UTC"


def effective_timezone(shop, tenant) -> str:
    """Return resolved IANA timezone: shop override → tenant → UTC."""
    if shop is not None and getattr(shop, "timezone", None):
        return shop.timezone
    if tenant is not None and getattr(tenant, "timezone", None):
        return tenant.timezone
    return FALLBACK_TZ


def validate_iana_timezone(tz: str) -> bool:
    """Return True if tz is a valid IANA timezone string."""
    return tz in available_timezones()


def fy_range(financial_year_start_month: int | None, reference_date: date) -> tuple[date, date]:
    """Return (fy_start, fy_end) for the financial year containing reference_date."""
    m = financial_year_start_month or 1
    year = reference_date.year
    fy_start = date(year, m, 1)
    if reference_date < fy_start:
        fy_start = date(year - 1, m, 1)
    fy_end = date(fy_start.year + 1, m, 1) - timedelta(days=1)
    return fy_start, fy_end
