"""FX service — the only place in the codebase that does cross-currency conversion.

Three responsibilities:
  - Read a stored rate (`get_rate`)
  - Upsert a rate (`set_rate`) — sets effective_at to now
  - Convert a Money instance to a target currency (`convert`)

Conversion rules:
  - Same-currency: no-op, no DB hit
  - Direct rate exists: amount × rate, rounded half-up to whole cents
  - Inverse rate exists: use 1/rate
  - Neither: raise ``FxRateMissingError``
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.money import Money, round_half_up_cents
from app.models import FxRate


class FxRateMissingError(LookupError):
    """No rate available (direct or inverse) for the requested pair."""


def _norm(code: str) -> str:
    return code.upper()


def get_rate(db: Session, tenant_id: UUID, from_currency: str, to_currency: str) -> Decimal | None:
    """Return the stored rate for the pair, or None if not found.

    Direct direction only — no inversion, no triangulation. Use ``convert`` for
    full conversion logic.
    """
    row = db.execute(
        select(FxRate).where(
            FxRate.tenant_id == tenant_id,
            FxRate.from_currency == _norm(from_currency),
            FxRate.to_currency == _norm(to_currency),
        )
    ).scalar_one_or_none()
    return Decimal(row.rate) if row is not None else None


def set_rate(
    db: Session,
    tenant_id: UUID,
    from_currency: str,
    to_currency: str,
    rate: Decimal,
) -> FxRate:
    """Upsert a rate. Bumps effective_at to now."""
    from datetime import UTC, datetime
    from_c = _norm(from_currency)
    to_c = _norm(to_currency)

    existing = db.execute(
        select(FxRate).where(
            FxRate.tenant_id == tenant_id,
            FxRate.from_currency == from_c,
            FxRate.to_currency == to_c,
        )
    ).scalar_one_or_none()

    now = datetime.now(UTC)
    if existing is not None:
        existing.rate = rate
        existing.effective_at = now
        db.flush()
        return existing

    row = FxRate(
        tenant_id=tenant_id,
        from_currency=from_c,
        to_currency=to_c,
        rate=rate,
        source="manual",
        effective_at=now,
    )
    db.add(row)
    db.flush()
    return row


def convert(db: Session, tenant_id: UUID, money: Money, target_currency: str) -> Money:
    """Convert a Money to a target currency.

    Same-currency: returns the input unchanged (no DB hit).
    Direct rate: amount_cents × rate, rounded half-up.
    Inverse rate: amount_cents × (1 / inverse_rate), rounded half-up.
    Neither: raise ``FxRateMissingError``.
    """
    target = _norm(target_currency)
    if money.currency_code == target:
        return money

    direct = get_rate(db, tenant_id, money.currency_code, target)
    if direct is not None:
        new_cents = round_half_up_cents(Decimal(money.amount_cents) * direct)
        return Money(new_cents, target)

    inverse = get_rate(db, tenant_id, target, money.currency_code)
    if inverse is not None and inverse != 0:
        new_cents = round_half_up_cents(Decimal(money.amount_cents) / inverse)
        return Money(new_cents, target)

    raise FxRateMissingError(
        f"No FX rate available for {money.currency_code} → {target} on tenant {tenant_id}"
    )
