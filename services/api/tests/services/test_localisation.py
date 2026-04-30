"""Tests for localisation helpers — no DB required."""
from __future__ import annotations

from datetime import date

import pytest


def test_effective_timezone_shop_override():
    from app.services.localisation import effective_timezone

    class FakeShop:
        timezone = "Asia/Kolkata"

    class FakeTenant:
        timezone = "America/Toronto"

    assert effective_timezone(FakeShop(), FakeTenant()) == "Asia/Kolkata"


def test_effective_timezone_tenant_fallback():
    from app.services.localisation import effective_timezone

    class FakeShop:
        timezone = None

    class FakeTenant:
        timezone = "America/Toronto"

    assert effective_timezone(FakeShop(), FakeTenant()) == "America/Toronto"


def test_effective_timezone_utc_fallback():
    from app.services.localisation import effective_timezone

    assert effective_timezone(None, None) == "UTC"


def test_validate_iana_valid():
    from app.services.localisation import validate_iana_timezone

    assert validate_iana_timezone("Asia/Kolkata") is True
    assert validate_iana_timezone("America/Toronto") is True
    assert validate_iana_timezone("UTC") is True


def test_validate_iana_invalid():
    from app.services.localisation import validate_iana_timezone

    assert validate_iana_timezone("Not/ATimezone") is False
    assert validate_iana_timezone("IST") is False


def test_fy_range_india_mid_year():
    from app.services.localisation import fy_range

    start, end = fy_range(4, date(2026, 8, 15))
    assert start == date(2026, 4, 1)
    assert end == date(2027, 3, 31)


def test_fy_range_india_before_april():
    from app.services.localisation import fy_range

    start, end = fy_range(4, date(2026, 1, 15))
    assert start == date(2025, 4, 1)
    assert end == date(2026, 3, 31)


def test_fy_range_january_fy():
    from app.services.localisation import fy_range

    start, end = fy_range(1, date(2026, 6, 15))
    assert start == date(2026, 1, 1)
    assert end == date(2026, 12, 31)


def test_fy_range_on_fy_start():
    from app.services.localisation import fy_range

    start, end = fy_range(4, date(2026, 4, 1))
    assert start == date(2026, 4, 1)
    assert end == date(2027, 3, 31)
