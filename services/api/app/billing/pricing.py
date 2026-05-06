"""Pricing resolver: given (product, currency, channel?), return Money.

Resolution order (highest priority first):
  1. ProductPrice with matching (product_id, channel_id, currency_code) — exact channel-specific
  2. ProductPrice with matching (product_id, currency_code, channel_id IS NULL) — tenant-wide
  3. FX-derived from Product.unit_price_cents (assumed in tenant.default_currency_code)

If neither a ProductPrice nor an FX rate is available, raises ``FxRateMissingError``.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.fx import convert
from app.billing.money import Money
from app.models import Product, ProductPrice, Tenant


def price_for_product_in_currency(
    db: Session,
    product_id: UUID,
    currency_code: str,
    *,
    channel_id: UUID | None = None,
) -> Money:
    """Resolve the price of a product in a target currency, optionally for a specific channel."""
    target = currency_code.upper()

    product = db.get(Product, product_id)
    if product is None:
        raise LookupError(f"Unknown product_id {product_id}")

    # 1. Channel-specific price for this currency
    if channel_id is not None:
        ch_specific = db.execute(
            select(ProductPrice).where(
                ProductPrice.product_id == product_id,
                ProductPrice.channel_id == channel_id,
                ProductPrice.currency_code == target,
            )
        ).scalar_one_or_none()
        if ch_specific is not None:
            return Money(ch_specific.amount_cents, target)

    # 2. Tenant-wide price for this currency
    tenant_wide = db.execute(
        select(ProductPrice).where(
            ProductPrice.product_id == product_id,
            ProductPrice.channel_id.is_(None),
            ProductPrice.currency_code == target,
        )
    ).scalar_one_or_none()
    if tenant_wide is not None:
        return Money(tenant_wide.amount_cents, target)

    # 3. FX-derive from Product.unit_price_cents (in tenant default currency)
    tenant = db.get(Tenant, product.tenant_id)
    base_currency = (tenant.default_currency_code if tenant else "USD") or "USD"
    base_money = Money(product.unit_price_cents, base_currency)
    return convert(db, product.tenant_id, base_money, target)
