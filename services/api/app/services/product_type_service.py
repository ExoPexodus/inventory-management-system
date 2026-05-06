"""Pure-function helpers that answer product-type-specific behavior questions."""
from __future__ import annotations

_SHIPPABLE_TYPES: frozenset[str] = frozenset({"physical"})
_NEVER_TRACKED_TYPES: frozenset[str] = frozenset({"service", "donation", "gift_card"})
_VARIABLE_AMOUNT_TYPES: frozenset[str] = frozenset({"donation"})
_TAX_EXEMPT_BY_DEFAULT_TYPES: frozenset[str] = frozenset({"donation"})


def is_shippable(product_type: str) -> bool:
    """Return True if the type normally requires a shipping address / carrier."""
    return product_type in _SHIPPABLE_TYPES


def is_inventory_tracked(product_type: str, *, track_quantity: bool) -> bool:
    """Return True if the product actively deducts from stock on sale.

    Types in _NEVER_TRACKED_TYPES are always untracked (unlimited).
    For physical and digital, the track_quantity flag controls stock deduction.
    """
    if product_type in _NEVER_TRACKED_TYPES:
        return False
    return track_quantity


def is_variable_amount(product_type: str) -> bool:
    """Return True if the shopper sets the price (e.g. open-amount donation)."""
    return product_type in _VARIABLE_AMOUNT_TYPES


def is_tax_exempt_by_default(product_type: str) -> bool:
    """Return True if the type is typically tax-exempt without explicit configuration."""
    return product_type in _TAX_EXEMPT_BY_DEFAULT_TYPES
