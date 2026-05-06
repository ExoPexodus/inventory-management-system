"""Money value type — the only typed money primitive in the codebase.

Use ``Money`` whenever you handle amounts that may cross currencies. Operations
between Money instances assert same-currency. The only legal way to convert is
via ``app.billing.fx.convert``.

Three rules:
1. Currency is pinned at the boundary (Order, Channel, ProductPrice). Don't
   reconvert internally.
2. ``fx.convert`` is the single seam for cross-currency math.
3. Cents amounts are integers. FX math uses Decimal then rounds to whole cents
   via ``round_half_up_cents``.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal


@dataclass(frozen=True)
class Money:
    """An amount of money in a specific currency.

    Frozen — once constructed, can't mutate. Currency is normalised to upper case.
    """
    amount_cents: int
    currency_code: str

    def __post_init__(self) -> None:
        if self.currency_code != self.currency_code.upper():
            object.__setattr__(self, "currency_code", self.currency_code.upper())

    def __add__(self, other: "Money") -> "Money":
        self._assert_same_currency(other)
        return Money(self.amount_cents + other.amount_cents, self.currency_code)

    def __sub__(self, other: "Money") -> "Money":
        self._assert_same_currency(other)
        return Money(self.amount_cents - other.amount_cents, self.currency_code)

    def _assert_same_currency(self, other: "Money") -> None:
        if self.currency_code != other.currency_code:
            raise ValueError(
                f"Cannot operate on mixed currency values: {self.currency_code} and "
                f"{other.currency_code}. Use app.billing.fx.convert first."
            )

    def __repr__(self) -> str:
        return f"Money({self.amount_cents} {self.currency_code})"


def round_half_up_cents(amount: float | Decimal) -> int:
    """Round a Decimal/float cents-amount to the nearest whole cent, half-up.

    Half-up: 0.5 → 1, -0.5 → 0 (toward positive infinity at .5 boundary).
    Standard retail rounding — matches POS rounding.

    Implementation: floor(x + 0.5) gives half-up-toward-+inf semantics for
    both positive and negative values, unlike Python's ROUND_HALF_UP which
    rounds away from zero (so -0.5 → -1 instead of 0).
    """
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    return int((amount + Decimal("0.5")).to_integral_value(rounding=ROUND_FLOOR))
