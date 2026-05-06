"""Shipping calculator service.

``calculate_shipping_options`` is the central function. Given a channel, a
destination country, and a cart, it finds all eligible shipping rates and
returns them as displayable options with prices in the requested currency.

Resolution flow:
1. Find all ShippingZones for the channel that cover the destination country.
   Specific zones (countries list includes the destination) beat catch-all zones.
2. For each matching zone, filter rates by shipping-class and conditions.
3. Convert rate prices to the requested currency via app.billing.fx.convert.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.fx import convert
from app.billing.money import Money
from app.models import Channel, Product, ShippingRate, ShippingZone
from app.services.product_type_service import is_shippable


def calculate_shipping_options(
    db: Session,
    *,
    channel_id: UUID,
    destination_country: str,
    cart_lines: list[dict[str, Any]],
    cart_subtotal_cents: int,
    currency: str,
) -> list[dict[str, Any]]:
    """Return displayable shipping options for a cart.

    Each option: {rate_id, zone_id, name, price_cents, currency_code, is_free}
    Returns [] when there are no shippable items or no matching zones/rates.
    """
    country = destination_country.upper()

    channel = db.get(Channel, channel_id)
    if channel is None:
        return []

    shippable_lines = _get_shippable_lines(db, cart_lines)
    if not shippable_lines:
        return []

    total_weight_grams = sum(
        (line["weight_grams"] or 0) * line["quantity"]
        for line in shippable_lines
    )
    total_item_count = sum(line["quantity"] for line in shippable_lines)
    cart_classes = {line["shipping_class"] for line in shippable_lines}

    zones = _find_matching_zones(db, channel_id, country)
    if not zones:
        return []

    options: list[dict[str, Any]] = []
    for zone in zones:
        rates = db.execute(
            select(ShippingRate).where(ShippingRate.zone_id == zone.id)
        ).scalars().all()

        for rate in rates:
            if not _rate_matches_classes(rate, cart_classes):
                continue
            if not _rate_condition_met(rate, cart_subtotal_cents, total_weight_grams, total_item_count):
                continue

            effective_cents = _effective_price(rate, cart_subtotal_cents)
            is_free = effective_cents == 0

            if rate.currency_code.upper() == currency.upper():
                final_cents = effective_cents
                final_currency = currency.upper()
            else:
                try:
                    converted = convert(
                        db,
                        channel.tenant_id,
                        Money(effective_cents, rate.currency_code),
                        currency,
                    )
                    final_cents = converted.amount_cents
                    final_currency = converted.currency_code
                except Exception:
                    continue

            options.append({
                "rate_id": rate.id,
                "zone_id": zone.id,
                "name": rate.name,
                "price_cents": final_cents,
                "currency_code": final_currency,
                "is_free": is_free,
            })

    return options


def _get_shippable_lines(db: Session, cart_lines: list[dict]) -> list[dict]:
    result = []
    for line in cart_lines:
        product = db.get(Product, line["product_id"])
        if product is None:
            continue
        if not is_shippable(product.product_type):
            continue
        result.append({
            "product_id": product.id,
            "quantity": line["quantity"],
            "unit_price_cents": line["unit_price_cents"],
            "weight_grams": product.weight_grams,
            "shipping_class": product.shipping_class,
        })
    return result


def _find_matching_zones(db: Session, channel_id: UUID, country: str) -> list[ShippingZone]:
    all_zones = db.execute(
        select(ShippingZone).where(ShippingZone.channel_id == channel_id)
    ).scalars().all()

    specific = [
        z for z in all_zones
        if z.countries and country in [c.upper() for c in z.countries]
    ]
    if specific:
        return specific

    return [z for z in all_zones if z.is_catch_all]


def _rate_matches_classes(rate: ShippingRate, cart_classes: set[str | None]) -> bool:
    if rate.applies_to_classes is None:
        return True
    allowed = set(rate.applies_to_classes)
    for cls in cart_classes:
        if cls is None:
            continue
        if cls not in allowed:
            return False
    return True


def _rate_condition_met(
    rate: ShippingRate,
    cart_subtotal_cents: int,
    total_weight_grams: int,
    total_item_count: int,
) -> bool:
    ct = rate.condition_type
    if ct == "none":
        return True

    if ct == "by_total":
        value = cart_subtotal_cents
    elif ct == "by_weight":
        value = total_weight_grams
    elif ct == "by_items":
        value = total_item_count
    else:
        return True

    lo = rate.condition_min
    hi = rate.condition_max
    if lo is not None and value < lo:
        return False
    if hi is not None and value > hi:
        return False
    return True


def _effective_price(rate: ShippingRate, cart_subtotal_cents: int) -> int:
    if rate.free_above_cents is not None and cart_subtotal_cents >= rate.free_above_cents:
        return 0
    return rate.base_price_cents
