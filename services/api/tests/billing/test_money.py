import pytest

from app.billing.money import Money, round_half_up_cents


def test_money_construction() -> None:
    m = Money(1999, "USD")
    assert m.amount_cents == 1999
    assert m.currency_code == "USD"


def test_money_currency_code_is_uppercased() -> None:
    """Construction normalises currency to upper-case so 'usd' and 'USD' compare equal."""
    m = Money(100, "usd")
    assert m.currency_code == "USD"


def test_money_addition_same_currency() -> None:
    a = Money(100, "USD")
    b = Money(50, "USD")
    assert (a + b) == Money(150, "USD")


def test_money_addition_different_currency_raises() -> None:
    a = Money(100, "USD")
    b = Money(50, "EUR")
    with pytest.raises(ValueError, match="currency"):
        a + b


def test_money_subtraction() -> None:
    a = Money(100, "USD")
    b = Money(40, "USD")
    assert (a - b) == Money(60, "USD")


def test_money_equality() -> None:
    assert Money(100, "USD") == Money(100, "USD")
    assert Money(100, "USD") != Money(100, "EUR")
    assert Money(100, "USD") != Money(101, "USD")


def test_money_is_frozen() -> None:
    """Frozen dataclass — direct attribute assignment fails."""
    import dataclasses
    m = Money(100, "USD")
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.amount_cents = 200  # type: ignore[misc]


def test_money_repr_is_human_readable() -> None:
    m = Money(1999, "USD")
    s = repr(m)
    assert "1999" in s
    assert "USD" in s


def test_round_half_up_cents_half_rounds_up() -> None:
    """0.5 cents always rounds up to 1 (not banker's rounding)."""
    assert round_half_up_cents(100.5) == 101
    assert round_half_up_cents(99.5) == 100


def test_round_half_up_cents_below_half_rounds_down() -> None:
    assert round_half_up_cents(100.4999) == 100


def test_round_half_up_cents_handles_negative() -> None:
    """Negative amounts also round 'half up' in absolute terms (toward +inf)."""
    assert round_half_up_cents(-100.5) == -100
    assert round_half_up_cents(-100.6) == -101


def test_round_half_up_cents_handles_decimal_input() -> None:
    """Accept Decimal inputs — FX math uses Decimal for precision."""
    from decimal import Decimal
    assert round_half_up_cents(Decimal("100.5")) == 101
    assert round_half_up_cents(Decimal("99.4")) == 99
