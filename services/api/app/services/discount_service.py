"""Discount application service."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.billing.money import round_half_up_cents
from app.models import Discount, DiscountUse


class DiscountNotFoundError(LookupError):
    """No matching active discount found for this code / tenant."""


class DiscountNotEligibleError(ValueError):
    """Discount found but conditions not met for this cart / customer."""


def apply_discount(
    db: Session,
    *,
    tenant_id: UUID,
    channel_id: UUID,
    cart_subtotal_cents: int,
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

    amount, is_free_shipping = _compute_amount(discount, cart_subtotal_cents)
    return {
        "discount_id": discount.id,
        "name": discount.name,
        "discount_type": discount.discount_type,
        "discount_amount_cents": amount,
        "final_total_cents": cart_subtotal_cents - amount,
        "is_free_shipping": is_free_shipping,
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


def _compute_amount(discount: Discount, cart_subtotal_cents: int) -> tuple[int, bool]:
    dt = discount.discount_type
    if dt == "free_shipping":
        return 0, True
    if dt == "percentage":
        raw = round_half_up_cents(cart_subtotal_cents * (discount.value_bps or 0) / 10000)
        return min(raw, cart_subtotal_cents), False
    if dt == "fixed_amount":
        return min(discount.value_cents or 0, cart_subtotal_cents), False
    return 0, False
