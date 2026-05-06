"""Tax calculator service.

``calculate_tax_for_cart`` computes line-item tax for a cart given a channel
and destination. Returns a breakdown per line (total tax + per-component split).

Tax inclusivity:
  channel.tax_included_in_price=False (default): exclusive — tax added on top.
    effective_tax = line_price * total_rate_bps / 10000
  channel.tax_included_in_price=True: inclusive — tax backed out of price.
    effective_tax = line_price * total_rate_bps / (10000 + total_rate_bps)

Region resolution: state-specific region takes priority over country-only.
If no region matches, all lines get 0 tax.
Donation product type → always tax-exempt regardless of region/class.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.money import round_half_up_cents
from app.models import Channel, Product, TaxRegion, TaxRule
from app.services.product_type_service import is_tax_exempt_by_default


def calculate_tax_for_cart(
    db: Session,
    *,
    channel_id: UUID,
    destination_country: str,
    cart_lines: list[dict[str, Any]],
    currency: str,
    destination_state: str | None = None,
) -> dict[str, Any]:
    """Compute tax for a cart. Returns {total_tax_cents, tax_included, lines}."""
    channel = db.get(Channel, channel_id)
    if channel is None:
        return _zero_result(cart_lines)

    tax_included = bool(channel.tax_included_in_price)
    country = destination_country.upper()
    state = destination_state.upper() if destination_state else None

    region = _find_region(db, channel.tenant_id, country, state)
    line_results = []

    for line in cart_lines:
        product = db.get(Product, line["product_id"])
        qty = line["quantity"]
        unit_price = line["unit_price_cents"]

        if product is None:
            line_results.append(_zero_line(line))
            continue

        if is_tax_exempt_by_default(product.product_type):
            line_results.append(_zero_line(line))
            continue

        tax_class = product.tax_class or "standard"
        rule = _find_rule(db, region, tax_class) if region else None
        components = rule.components if rule else []

        line_tax, component_breakdown = _compute_tax(unit_price, qty, components, tax_included)

        line_results.append({
            "product_id": product.id,
            "quantity": qty,
            "unit_price_cents": unit_price,
            "price_before_tax_cents": unit_price if not tax_included else (unit_price - round_half_up_cents(unit_price * _total_rate(components) / (10000 + _total_rate(components)))) if components else unit_price,
            "tax_cents": line_tax,
            "components": component_breakdown,
        })

    total_tax = sum(ln["tax_cents"] for ln in line_results)
    return {"total_tax_cents": total_tax, "tax_included": tax_included, "lines": line_results}


def _find_region(db: Session, tenant_id: UUID, country: str, state: str | None) -> TaxRegion | None:
    regions = db.execute(
        select(TaxRegion).where(
            TaxRegion.tenant_id == tenant_id,
            TaxRegion.country_code == country,
        )
    ).scalars().all()

    if state:
        state_match = next((r for r in regions if r.state_code and r.state_code.upper() == state), None)
        if state_match:
            return state_match

    return next((r for r in regions if r.state_code is None), None)


def _find_rule(db: Session, region: TaxRegion, tax_class: str) -> TaxRule | None:
    return db.execute(
        select(TaxRule).where(
            TaxRule.region_id == region.id,
            TaxRule.tax_class == tax_class,
        )
    ).scalar_one_or_none()


def _total_rate(components: list[dict]) -> int:
    return sum(c["rate_bps"] for c in components)


def _compute_tax(unit_price: int, quantity: int, components: list[dict], tax_included: bool) -> tuple[int, list[dict]]:
    total_rate_bps = _total_rate(components)
    line_total = unit_price * quantity

    if total_rate_bps == 0 or not components:
        return 0, []

    if tax_included:
        effective_tax = round_half_up_cents(line_total * total_rate_bps / (10000 + total_rate_bps))
    else:
        effective_tax = round_half_up_cents(line_total * total_rate_bps / 10000)

    breakdown = []
    allocated = 0
    for i, comp in enumerate(components):
        if i == len(components) - 1:
            comp_tax = effective_tax - allocated
        else:
            comp_tax = round_half_up_cents(effective_tax * comp["rate_bps"] / total_rate_bps)
        breakdown.append({"label": comp["label"], "tax_cents": comp_tax})
        allocated += comp_tax

    return effective_tax, breakdown


def _zero_line(line: dict) -> dict:
    return {
        "product_id": line["product_id"],
        "quantity": line["quantity"],
        "unit_price_cents": line["unit_price_cents"],
        "price_before_tax_cents": line["unit_price_cents"],
        "tax_cents": 0,
        "components": [],
    }


def _zero_result(cart_lines: list[dict]) -> dict:
    return {"total_tax_cents": 0, "tax_included": False, "lines": [_zero_line(ln) for ln in cart_lines]}
