"""Discount application service."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.billing.money import round_half_up_cents
from app.models import Discount, DiscountTier, DiscountUse


class DiscountNotFoundError(LookupError):
    """No matching active discount found for this code / tenant."""


class DiscountNotEligibleError(ValueError):
    """Discount found but conditions not met for this cart / customer."""


@dataclass
class CartLine:
    product_id: UUID
    quantity: int
    unit_price_cents: int


def apply_discount(
    db: Session,
    *,
    tenant_id: UUID,
    channel_id: UUID,
    cart_subtotal_cents: int,
    cart_lines: list[CartLine] | None = None,
    code: str | None = None,
    customer_id: UUID | None = None,
) -> dict[str, Any]:
    """Validate a discount and compute the amount. Does NOT write a DiscountUse row."""
    discount = _find_discount(db, tenant_id, channel_id, code)
    _check_window(discount)
    _check_min_subtotal(discount, cart_subtotal_cents)
    _check_global_limit(db, discount)
    if customer_id:
        _check_customer_limit(db, discount, customer_id)

    # free_shipping bypasses all condition/tier logic
    if discount.discount_type == "free_shipping":
        return {
            "discount_id": discount.id,
            "name": discount.name,
            "discount_type": discount.discount_type,
            "discount_amount_cents": 0,
            "final_total_cents": cart_subtotal_cents,
            "is_free_shipping": True,
        }

    # Check if discount has tiers or conditions that require cart_lines
    tiers = _load_tiers(db, discount.id)
    has_conditions = bool(
        discount.condition_category_id
        or discount.condition_tag
        or discount.condition_quantity_scope != "none"
    )
    has_tiers = bool(tiers)

    if (has_tiers or has_conditions) and cart_lines is None:
        raise DiscountNotEligibleError("Discount requires cart line context")

    # Filter cart lines to qualifying lines (category/tag conditions)
    if cart_lines is not None and has_conditions:
        qualifying_lines = _filter_qualifying_lines(db, discount, cart_lines)
    elif cart_lines is not None:
        qualifying_lines = cart_lines
    else:
        qualifying_lines = None

    # Compute qualifying subtotal
    if qualifying_lines is not None:
        qualifying_subtotal = sum(
            line.unit_price_cents * line.quantity for line in qualifying_lines
        )
    else:
        qualifying_subtotal = cart_subtotal_cents

    # Compute qualifying quantity for tier resolution / quantity gate
    if qualifying_lines is not None:
        qualifying_quantity = _compute_qualifying_quantity(
            discount.condition_quantity_scope, qualifying_lines
        )
    else:
        qualifying_quantity = 0

    # Quantity gate
    if discount.condition_min_quantity is not None and qualifying_lines is not None:
        if qualifying_quantity < discount.condition_min_quantity:
            raise DiscountNotEligibleError(
                f"Minimum quantity {discount.condition_min_quantity} not met "
                f"(qualifying quantity is {qualifying_quantity})"
            )

    # Resolve tier or use parent value
    if has_tiers:
        value_bps, value_cents = _resolve_tier(tiers, qualifying_quantity)
    else:
        value_bps = discount.value_bps
        value_cents = discount.value_cents

    amount = _compute_amount(discount.discount_type, qualifying_subtotal, value_bps, value_cents)
    # Final safety cap against cart total
    amount = min(amount, cart_subtotal_cents)

    return {
        "discount_id": discount.id,
        "name": discount.name,
        "discount_type": discount.discount_type,
        "discount_amount_cents": amount,
        "final_total_cents": cart_subtotal_cents - amount,
        "is_free_shipping": False,
    }


def record_discount_use(
    db: Session,
    *,
    tenant_id: UUID,
    discount_id: UUID,
    discount_amount_cents: int,
    cart_token: str | None = None,
    customer_id: UUID | None = None,
    order_id: UUID | None = None,
) -> DiscountUse:
    use = DiscountUse(
        tenant_id=tenant_id,
        discount_id=discount_id,
        cart_token=cart_token,
        customer_id=customer_id,
        order_id=order_id,
        discount_amount_cents=discount_amount_cents,
    )
    db.add(use)
    db.flush()
    return use


def _find_discount(db: Session, tenant_id: UUID, channel_id: UUID, code: str | None) -> Discount:
    q = select(Discount).where(
        Discount.tenant_id == tenant_id,
        Discount.status == "active",
    )
    if code is not None:
        q = q.where(func.upper(Discount.code) == code.upper())
    else:
        q = q.where(Discount.code.is_(None))

    q = q.where(
        (Discount.channel_id == channel_id) | (Discount.channel_id.is_(None))
    )
    q = q.order_by(Discount.priority.desc(), Discount.value_bps.desc().nullslast(),
                   Discount.value_cents.desc().nullslast())

    discount = db.execute(q).scalars().first()
    if discount is None:
        raise DiscountNotFoundError(
            f"No active discount found for code={code!r} on tenant {tenant_id}"
        )
    return discount


def _check_window(discount: Discount) -> None:
    now = datetime.now(UTC)
    if discount.starts_at and discount.starts_at > now:
        raise DiscountNotEligibleError(
            f"Discount {discount.code!r} is not yet valid (starts {discount.starts_at.isoformat()})"
        )
    if discount.expires_at and discount.expires_at <= now:
        raise DiscountNotEligibleError(
            f"Discount {discount.code!r} has expired"
        )


def _check_min_subtotal(discount: Discount, cart_subtotal_cents: int) -> None:
    if discount.min_subtotal_cents and cart_subtotal_cents < discount.min_subtotal_cents:
        raise DiscountNotEligibleError(
            f"Cart minimum {discount.min_subtotal_cents} not met (cart is {cart_subtotal_cents})"
        )


def _check_global_limit(db: Session, discount: Discount) -> None:
    if discount.max_uses_total is None:
        return
    count = db.execute(
        select(func.count(DiscountUse.id)).where(DiscountUse.discount_id == discount.id)
    ).scalar_one()
    if count >= discount.max_uses_total:
        raise DiscountNotEligibleError(
            f"Discount {discount.code!r} has reached its global usage limit"
        )


def _check_customer_limit(db: Session, discount: Discount, customer_id: UUID) -> None:
    if discount.max_uses_per_customer is None:
        return
    count = db.execute(
        select(func.count(DiscountUse.id)).where(
            DiscountUse.discount_id == discount.id,
            DiscountUse.customer_id == customer_id,
        )
    ).scalar_one()
    if count >= discount.max_uses_per_customer:
        raise DiscountNotEligibleError(
            f"Discount {discount.code!r} has reached its per-customer usage limit"
        )


def _load_tiers(db: Session, discount_id: UUID) -> list[DiscountTier]:
    return list(db.execute(
        select(DiscountTier)
        .where(DiscountTier.discount_id == discount_id)
        .order_by(DiscountTier.threshold_quantity.desc())
    ).scalars().all())


def _filter_qualifying_lines(
    db: Session, discount: Discount, cart_lines: list[CartLine]
) -> list[CartLine]:
    """Return the subset of cart_lines that match the discount's category/tag conditions."""
    from app.models import Product, ProductCategory

    qualifying_ids: set[UUID] | None = None

    if discount.condition_category_id:
        cat_product_ids = set(db.execute(
            select(ProductCategory.product_id).where(
                ProductCategory.category_id == discount.condition_category_id
            )
        ).scalars().all())
        qualifying_ids = cat_product_ids if qualifying_ids is None else qualifying_ids & cat_product_ids

    if discount.condition_tag:
        tag = discount.condition_tag.lower()
        tag_product_ids = set(db.execute(
            select(Product.id).where(
                Product.tags.op("?")(tag)
            )
        ).scalars().all())
        qualifying_ids = tag_product_ids if qualifying_ids is None else qualifying_ids & tag_product_ids

    if qualifying_ids is None:
        # No category/tag condition — all lines qualify
        return cart_lines

    return [line for line in cart_lines if line.product_id in qualifying_ids]


def _compute_qualifying_quantity(scope: str, lines: list[CartLine]) -> int:
    """Compute quantity for tier/gate resolution based on scope."""
    if not lines:
        return 0
    if scope == "per_line":
        return max(line.quantity for line in lines)
    # "cart_total" or "none"
    return sum(line.quantity for line in lines)


def _resolve_tier(tiers: list[DiscountTier], qualifying_quantity: int) -> tuple[int | None, int | None]:
    """
    Return (value_bps, value_cents) from the highest matching tier.
    Tiers are pre-sorted by threshold_quantity DESC.
    Raises DiscountNotEligibleError if no tier matches.
    """
    for tier in tiers:
        if qualifying_quantity >= tier.threshold_quantity:
            return tier.value_bps, tier.value_cents
    raise DiscountNotEligibleError(
        f"No discount tier matches quantity {qualifying_quantity}"
    )


def _compute_amount(
    discount_type: str,
    qualifying_subtotal: int,
    value_bps: int | None,
    value_cents: int | None,
) -> int:
    if discount_type == "percentage":
        raw = round_half_up_cents(qualifying_subtotal * (value_bps or 0) / 10000)
        return min(raw, qualifying_subtotal)
    if discount_type == "fixed_amount":
        return min(value_cents or 0, qualifying_subtotal)
    return 0
