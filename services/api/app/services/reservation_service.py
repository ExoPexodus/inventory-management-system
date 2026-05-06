"""Stock reservation engine: reserve, commit, release, sweep_expired."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Channel, StockMovement, StockReservation


DEFAULT_CART_TTL_SECONDS = 15 * 60          # 15 minutes
DEFAULT_PAYMENT_TTL_SECONDS = 24 * 60 * 60  # 24 hours


def _resolve_ttl_seconds(channel: Channel, purpose: str) -> int:
    """Pick the TTL for this channel + purpose.

    Looks up Channel.config[{purpose}_ttl_seconds] if present, else falls back
    to the module-level default for that purpose.
    """
    config = channel.config or {}
    if purpose == "payment_pending":
        return int(config.get("payment_ttl_seconds", DEFAULT_PAYMENT_TTL_SECONDS))
    return int(config.get("cart_ttl_seconds", DEFAULT_CART_TTL_SECONDS))


def reserve(
    db: Session,
    *,
    tenant_id: UUID,
    channel_id: UUID,
    product_id: UUID,
    shop_id: UUID,
    quantity: int,
    cart_token: str,
    purpose: str = "cart",
) -> StockReservation:
    """Create or update a reservation for a (channel, cart_token, product, shop) line.

    If a reservation for that exact key already exists, its quantity, expiry, and
    status are updated (and status is forced back to 'active' even if it had
    expired — the caller is asserting they want this hold now).
    """
    channel = db.get(Channel, channel_id)
    if channel is None:
        raise ValueError(f"Unknown channel_id {channel_id}")

    ttl = _resolve_ttl_seconds(channel, purpose)
    new_expiry = datetime.now(UTC) + timedelta(seconds=ttl)

    existing = db.execute(
        select(StockReservation).where(
            StockReservation.channel_id == channel_id,
            StockReservation.cart_token == cart_token,
            StockReservation.product_id == product_id,
            StockReservation.shop_id == shop_id,
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.quantity = quantity
        existing.purpose = purpose
        existing.status = "active"
        existing.expires_at = new_expiry
        db.flush()
        return existing

    res = StockReservation(
        tenant_id=tenant_id,
        channel_id=channel_id,
        product_id=product_id,
        shop_id=shop_id,
        quantity=quantity,
        cart_token=cart_token,
        purpose=purpose,
        status="active",
        expires_at=new_expiry,
    )
    db.add(res)
    db.flush()
    return res


def commit_reservation(db: Session, reservation_id: UUID) -> StockMovement | None:
    """Convert an active reservation to a real stock_movements row.

    Returns None if the reservation is not active (already committed, released, or expired).
    """
    res = db.get(StockReservation, reservation_id)
    if res is None or res.status != "active":
        return None

    res.status = "committed"
    movement = StockMovement(
        tenant_id=res.tenant_id,
        shop_id=res.shop_id,
        product_id=res.product_id,
        quantity_delta=-res.quantity,
        movement_type="sale",
        idempotency_key=f"reservation-{res.id}",
        source_channel_id=res.channel_id,
    )
    db.add(movement)
    db.flush()
    return movement


def release_reservation(db: Session, reservation_id: UUID) -> bool:
    """Mark an active reservation as released. Returns True if changed."""
    res = db.get(StockReservation, reservation_id)
    if res is None or res.status != "active":
        return False
    res.status = "released"
    db.flush()
    return True


def sweep_expired(db: Session) -> int:
    """Mark all past-expiry active reservations as 'expired'. Returns count flipped."""
    now = datetime.now(UTC)
    result = db.execute(
        update(StockReservation)
        .where(
            StockReservation.status == "active",
            StockReservation.expires_at <= now,
        )
        .values(status="expired", updated_at=now)
    )
    db.flush()
    return result.rowcount or 0
