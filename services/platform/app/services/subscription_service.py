"""Subscription lifecycle state machine and helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tables import (
    Addon,
    Plan,
    PlatformTenant,
    Subscription,
    SubscriptionAddon,
    TenantLimitOverride,
)

# ---------------------------------------------------------------------------
# Valid status transitions
# ---------------------------------------------------------------------------

VALID_TRANSITIONS: dict[str, set[str]] = {
    "trial": {"active", "past_due", "cancelled"},
    "active": {"past_due", "suspended", "cancelled"},
    "past_due": {"active", "expired", "cancelled"},
    "expired": {"active"},  # reactivation with new payment
    "suspended": {"active", "cancelled"},
    "cancelled": set(),  # terminal
}


def can_transition(current: str, target: str) -> bool:
    return target in VALID_TRANSITIONS.get(current, set())


# ---------------------------------------------------------------------------
# Create subscription
# ---------------------------------------------------------------------------


def create_subscription(
    db: Session,
    *,
    tenant_id: UUID,
    plan_id: UUID,
    billing_cycle: str = "monthly",
    is_trial: bool = False,
    trial_days: int = 14,
    grace_period_days: int = 7,
) -> Subscription:
    # Verify tenant and plan exist
    tenant = db.get(PlatformTenant, tenant_id)
    if tenant is None:
        raise ValueError("Tenant not found")
    plan = db.get(Plan, plan_id)
    if plan is None:
        raise ValueError("Plan not found")

    now = datetime.now(UTC)

    if is_trial:
        trial_end = now + timedelta(days=trial_days)
        sub = Subscription(
            tenant_id=tenant_id,
            plan_id=plan_id,
            status="trial",
            billing_cycle=billing_cycle,
            trial_ends_at=trial_end,
            current_period_start=now,
            current_period_end=trial_end,
            grace_period_days=grace_period_days,
        )
    else:
        period_end = _period_end(now, billing_cycle)
        sub = Subscription(
            tenant_id=tenant_id,
            plan_id=plan_id,
            status="active",
            billing_cycle=billing_cycle,
            current_period_start=now,
            current_period_end=period_end,
            grace_period_days=grace_period_days,
        )

    db.add(sub)
    db.flush()
    return sub


# ---------------------------------------------------------------------------
# Transition helpers
# ---------------------------------------------------------------------------


def transition_status(db: Session, sub: Subscription, new_status: str) -> Subscription:
    if not can_transition(sub.status, new_status):
        raise ValueError(f"Cannot transition from '{sub.status}' to '{new_status}'")

    now = datetime.now(UTC)
    sub.status = new_status
    sub.updated_at = now

    if new_status == "cancelled":
        sub.cancelled_at = now
    elif new_status == "active" and sub.status in ("expired", "past_due", "suspended"):
        # Reactivation — start a new billing period
        sub.current_period_start = now
        sub.current_period_end = _period_end(now, sub.billing_cycle)

    return sub


def activate_subscription(db: Session, sub: Subscription) -> Subscription:
    """Move trial/past_due/expired/suspended → active with a fresh period."""
    now = datetime.now(UTC)
    if not can_transition(sub.status, "active"):
        raise ValueError(f"Cannot activate from '{sub.status}'")
    sub.status = "active"
    sub.current_period_start = now
    sub.current_period_end = _period_end(now, sub.billing_cycle)
    sub.updated_at = now
    return sub


def suspend_subscription(db: Session, sub: Subscription) -> Subscription:
    return transition_status(db, sub, "suspended")


def cancel_subscription(db: Session, sub: Subscription) -> Subscription:
    return transition_status(db, sub, "cancelled")


# ---------------------------------------------------------------------------
# Add-on management
# ---------------------------------------------------------------------------


def add_addon(db: Session, subscription_id: UUID, addon_id: UUID) -> SubscriptionAddon:
    # Check addon exists
    addon = db.get(Addon, addon_id)
    if addon is None:
        raise ValueError("Addon not found")

    existing = db.execute(
        select(SubscriptionAddon).where(
            SubscriptionAddon.subscription_id == subscription_id,
            SubscriptionAddon.addon_id == addon_id,
            SubscriptionAddon.removed_at.is_(None),
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ValueError("Addon already active on this subscription")

    sa = SubscriptionAddon(subscription_id=subscription_id, addon_id=addon_id)
    db.add(sa)
    db.flush()
    return sa


def remove_addon(db: Session, subscription_id: UUID, addon_id: UUID) -> None:
    row = db.execute(
        select(SubscriptionAddon).where(
            SubscriptionAddon.subscription_id == subscription_id,
            SubscriptionAddon.addon_id == addon_id,
            SubscriptionAddon.removed_at.is_(None),
        )
    ).scalar_one_or_none()
    if row is None:
        raise ValueError("Addon not found on this subscription")
    row.removed_at = datetime.now(UTC)


# ---------------------------------------------------------------------------
# License state assembly
# ---------------------------------------------------------------------------


def build_license_state(db: Session, tenant_id: UUID) -> dict | None:
    """Assemble the full license state for a tenant. Returns None if no subscription."""
    sub = db.execute(
        select(Subscription)
        .where(Subscription.tenant_id == tenant_id)
        .order_by(Subscription.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if sub is None:
        return None

    plan = db.get(Plan, sub.plan_id)

    # Active addons
    addon_rows = db.execute(
        select(SubscriptionAddon, Addon)
        .join(Addon, Addon.id == SubscriptionAddon.addon_id)
        .where(
            SubscriptionAddon.subscription_id == sub.id,
            SubscriptionAddon.removed_at.is_(None),
        )
    ).all()
    active_addons = [a.codename for _, a in addon_rows]

    # Limit overrides
    overrides = db.execute(
        select(TenantLimitOverride).where(TenantLimitOverride.tenant_id == tenant_id)
    ).scalars().all()
    override_map = {o.limit_key: o.limit_value for o in overrides}

    # Grace period check
    now = datetime.now(UTC)
    is_in_grace = False
    if sub.status == "past_due" and sub.current_period_end:
        grace_end = sub.current_period_end + timedelta(days=sub.grace_period_days)
        is_in_grace = now <= grace_end
        if now > grace_end and sub.status == "past_due":
            sub.status = "expired"
            sub.updated_at = now

    return {
        "subscription_status": sub.status,
        "plan_codename": plan.codename if plan else "unknown",
        "billing_cycle": sub.billing_cycle,
        "active_addons": active_addons,
        "max_shops": override_map.get("max_shops", plan.max_shops if plan else 1),
        "max_employees": override_map.get("max_employees", plan.max_employees if plan else 5),
        "storage_limit_mb": override_map.get("storage_limit_mb", plan.storage_limit_mb if plan else 500),
        "trial_ends_at": sub.trial_ends_at.isoformat() if sub.trial_ends_at else None,
        "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
        "grace_period_days": sub.grace_period_days,
        "is_in_grace_period": is_in_grace,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _period_end(start: datetime, cycle: str) -> datetime:
    if cycle == "yearly":
        return start.replace(year=start.year + 1)
    # monthly
    month = start.month + 1
    year = start.year
    if month > 12:
        month = 1
        year += 1
    day = min(start.day, 28)  # safe for all months
    return start.replace(year=year, month=month, day=day)
