"""Auto-resolve reconciliation variances under tenant-configured thresholds."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import ShiftClosing, Shop, Tenant
from app.services.tenant_system_user import get_tenant_system_user

AUTO_RESOLVED_PREFIX = "[AUTO-RESOLVED"


def _effective_thresholds(tenant: Tenant, shop: Shop) -> tuple[int, int]:
    """Return (shortage_threshold, overage_threshold) applying shop overrides."""
    shortage = (
        shop.auto_resolve_shortage_cents_override
        if shop.auto_resolve_shortage_cents_override is not None
        else tenant.auto_resolve_shortage_cents
    )
    overage = (
        shop.auto_resolve_overage_cents_override
        if shop.auto_resolve_overage_cents_override is not None
        else tenant.auto_resolve_overage_cents
    )
    return shortage, overage


def maybe_auto_resolve_shift(
    db: Session, shift: ShiftClosing, tenant: Tenant, shop: Shop
) -> bool:
    """Append an auto-resolve note to shift.notes iff variance is within threshold.

    Returns True if the shift was auto-resolved, False otherwise. Caller commits.
    """
    discrepancy = shift.discrepancy_cents
    if discrepancy == 0:
        return False

    shortage_threshold, overage_threshold = _effective_thresholds(tenant, shop)

    if discrepancy < 0:
        threshold = shortage_threshold
        direction = "shortage"
        scope_overridden = shop.auto_resolve_shortage_cents_override is not None
    else:
        threshold = overage_threshold
        direction = "overage"
        scope_overridden = shop.auto_resolve_overage_cents_override is not None

    if threshold <= 0 or abs(discrepancy) > threshold:
        return False

    system_user = get_tenant_system_user(db, tenant.id)
    if system_user is None:
        raise RuntimeError(
            f"Cannot auto-resolve: no system user seeded for tenant {tenant.id}"
        )

    scope = "shop" if scope_overridden else "tenant"
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    note = (
        f"\n{AUTO_RESOLVED_PREFIX} by {system_user.email} on {timestamp}] "
        f"Variance {discrepancy:+d} within {scope} {direction} threshold of {threshold}."
    )
    shift.notes = (shift.notes or "") + note
    return True
