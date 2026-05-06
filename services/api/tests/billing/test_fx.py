import uuid
from decimal import Decimal

import pytest

from app.billing.money import Money
from app.models import FxRate, Tenant


def test_get_rate_returns_none_when_pair_unknown(db, tenant: Tenant) -> None:
    from app.billing.fx import get_rate
    assert get_rate(db, tenant.id, "USD", "INR") is None


def test_set_rate_creates_new(db, tenant: Tenant) -> None:
    from app.billing.fx import get_rate, set_rate
    set_rate(db, tenant.id, "USD", "INR", Decimal("83.25"))
    db.flush()
    rate = get_rate(db, tenant.id, "USD", "INR")
    assert rate == Decimal("83.25")


def test_set_rate_updates_existing(db, tenant: Tenant) -> None:
    """Setting the same pair twice updates the existing row (no duplicate)."""
    from sqlalchemy import select
    from app.billing.fx import set_rate

    set_rate(db, tenant.id, "USD", "INR", Decimal("82.00"))
    set_rate(db, tenant.id, "USD", "INR", Decimal("83.50"))
    db.flush()

    rows = db.execute(
        select(FxRate).where(
            FxRate.tenant_id == tenant.id,
            FxRate.from_currency == "USD",
            FxRate.to_currency == "INR",
        )
    ).scalars().all()
    assert len(rows) == 1
    assert Decimal(rows[0].rate) == Decimal("83.50")


def test_convert_same_currency_is_identity(db, tenant: Tenant) -> None:
    """Same-currency conversion is a no-op without touching FX table."""
    from app.billing.fx import convert
    m = Money(1999, "USD")
    converted = convert(db, tenant.id, m, "USD")
    assert converted == m


def test_convert_uses_stored_rate(db, tenant: Tenant) -> None:
    from app.billing.fx import convert, set_rate

    set_rate(db, tenant.id, "USD", "INR", Decimal("83.25"))
    db.flush()

    # 100 USD -> 8325 INR (cents-to-cents)
    result = convert(db, tenant.id, Money(100_00, "USD"), "INR")
    assert result.currency_code == "INR"
    # 100 USD = 100 * 83.25 = 8325 INR
    assert result.amount_cents == 8325_00


def test_convert_rounds_half_up(db, tenant: Tenant) -> None:
    """A rate that produces fractional cents rounds half-up."""
    from app.billing.fx import convert, set_rate

    set_rate(db, tenant.id, "USD", "EUR", Decimal("1.005"))
    db.flush()

    # 100 USD cents × 1.005 = 100.5 EUR cents → rounds to 101
    result = convert(db, tenant.id, Money(100, "USD"), "EUR")
    assert result == Money(101, "EUR")


def test_convert_uses_inverse_rate_when_only_reverse_pair_stored(db, tenant: Tenant) -> None:
    """If USD→INR is unknown but INR→USD is stored, convert via inversion."""
    from app.billing.fx import convert, set_rate

    set_rate(db, tenant.id, "INR", "USD", Decimal("0.012"))  # 1 INR = 0.012 USD
    db.flush()

    # 1000 INR -> ? USD. 1000 * 0.012 = 12 USD = 1200 cents
    result = convert(db, tenant.id, Money(1000_00, "INR"), "USD")
    assert result.currency_code == "USD"
    assert result.amount_cents == 1200


def test_convert_raises_when_no_rate_available(db, tenant: Tenant) -> None:
    """No rate for either direction → raise so caller knows to handle."""
    from app.billing.fx import FxRateMissingError, convert
    with pytest.raises(FxRateMissingError, match="USD.*JPY"):
        convert(db, tenant.id, Money(100, "USD"), "JPY")


def test_set_rate_normalises_currency_codes_to_upper(db, tenant: Tenant) -> None:
    from app.billing.fx import get_rate, set_rate
    set_rate(db, tenant.id, "usd", "inr", Decimal("83.0"))
    db.flush()
    assert get_rate(db, tenant.id, "USD", "INR") == Decimal("83.0")
