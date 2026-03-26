"""Per-shop tax resolution: shop_product_tax override, else shop default."""

from __future__ import annotations

from uuid import UUID

from app.models import Product, Shop, ShopProductTax


def line_tax_cents(line_subtotal_cents: int, effective_rate_bps: int) -> int:
    """Round half up to nearest cent."""
    if effective_rate_bps <= 0 or line_subtotal_cents <= 0:
        return 0
    return (line_subtotal_cents * effective_rate_bps + 5000) // 10000


def effective_tax_bps_for_product(
    shop: Shop,
    product: Product,
    override: ShopProductTax | None,
) -> tuple[int, bool]:
    """Returns (effective_tax_rate_bps, tax_exempt). When exempt, bps is 0."""
    if override is not None:
        if override.tax_exempt:
            return 0, True
        if override.effective_tax_rate_bps is not None:
            return max(0, override.effective_tax_rate_bps), False
    return max(0, shop.default_tax_rate_bps), False


def sale_tax_totals(
    shop: Shop,
    lines: list[tuple[Product, int, int]],
    overrides: dict[UUID, ShopProductTax],
) -> tuple[int, int]:
    """
    lines: (product, quantity, unit_price_cents)
    Returns (subtotal_cents, tax_cents).
    """
    subtotal = 0
    tax = 0
    for prod, qty, price in lines:
        line_sub = qty * price
        subtotal += line_sub
        ov = overrides.get(prod.id)
        bps, exempt = effective_tax_bps_for_product(shop, prod, ov)
        if exempt:
            continue
        tax += line_tax_cents(line_sub, bps)
    return subtotal, tax
