from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models import ShiftClosing, Shop, Tenant
from app.services.reconciliation_auto_resolve import (
    AUTO_RESOLVED_PREFIX,
    maybe_auto_resolve_shift,
)
from app.services.tenant_system_user import seed_tenant_system_user


def _make_shift(
    db: Session,
    tenant: Tenant,
    shop: Shop,
    discrepancy: int,
) -> ShiftClosing:
    shift = ShiftClosing(
        id=uuid4(),
        tenant_id=tenant.id,
        shop_id=shop.id,
        opened_at=datetime.now(UTC),
        closed_at=datetime.now(UTC),
        expected_cash_cents=10000,
        reported_cash_cents=10000 + discrepancy,
        discrepancy_cents=discrepancy,
        status="closed",
    )
    db.add(shift)
    db.flush()
    return shift


def test_zero_variance_does_not_append_note(db: Session, tenant: Tenant, shop: Shop) -> None:
    tenant.auto_resolve_shortage_cents = 5000
    tenant.auto_resolve_overage_cents = 5000
    seed_tenant_system_user(db, tenant.id)
    db.flush()
    shift = _make_shift(db, tenant, shop, discrepancy=0)

    assert maybe_auto_resolve_shift(db, shift, tenant, shop) is False
    assert shift.notes is None or AUTO_RESOLVED_PREFIX not in (shift.notes or "")


def test_shortage_within_threshold_auto_resolves(db: Session, tenant: Tenant, shop: Shop) -> None:
    tenant.auto_resolve_shortage_cents = 5000
    seed_tenant_system_user(db, tenant.id)
    db.flush()
    shift = _make_shift(db, tenant, shop, discrepancy=-4000)

    assert maybe_auto_resolve_shift(db, shift, tenant, shop) is True
    assert AUTO_RESOLVED_PREFIX in (shift.notes or "")
    assert "system+" in shift.notes
    assert "-4000" in shift.notes
    assert "shortage" in shift.notes


def test_overage_within_threshold_auto_resolves(db: Session, tenant: Tenant, shop: Shop) -> None:
    tenant.auto_resolve_overage_cents = 5000
    seed_tenant_system_user(db, tenant.id)
    db.flush()
    shift = _make_shift(db, tenant, shop, discrepancy=4000)

    assert maybe_auto_resolve_shift(db, shift, tenant, shop) is True
    assert AUTO_RESOLVED_PREFIX in (shift.notes or "")
    assert "overage" in shift.notes


def test_variance_exactly_at_threshold_is_inclusive(db: Session, tenant: Tenant, shop: Shop) -> None:
    tenant.auto_resolve_shortage_cents = 5000
    seed_tenant_system_user(db, tenant.id)
    db.flush()
    shift = _make_shift(db, tenant, shop, discrepancy=-5000)

    assert maybe_auto_resolve_shift(db, shift, tenant, shop) is True


def test_variance_over_threshold_does_not_resolve(db: Session, tenant: Tenant, shop: Shop) -> None:
    tenant.auto_resolve_shortage_cents = 5000
    seed_tenant_system_user(db, tenant.id)
    db.flush()
    shift = _make_shift(db, tenant, shop, discrepancy=-5001)

    assert maybe_auto_resolve_shift(db, shift, tenant, shop) is False
    assert shift.notes is None or AUTO_RESOLVED_PREFIX not in (shift.notes or "")


def test_threshold_of_zero_disables_direction(db: Session, tenant: Tenant, shop: Shop) -> None:
    tenant.auto_resolve_shortage_cents = 0
    tenant.auto_resolve_overage_cents = 5000
    seed_tenant_system_user(db, tenant.id)
    db.flush()
    shift = _make_shift(db, tenant, shop, discrepancy=-1)

    assert maybe_auto_resolve_shift(db, shift, tenant, shop) is False


def test_shop_override_wins_over_tenant(db: Session, tenant: Tenant, shop: Shop) -> None:
    tenant.auto_resolve_shortage_cents = 5000
    shop.auto_resolve_shortage_cents_override = 100
    seed_tenant_system_user(db, tenant.id)
    db.flush()
    shift = _make_shift(db, tenant, shop, discrepancy=-200)

    assert maybe_auto_resolve_shift(db, shift, tenant, shop) is False


def test_shop_override_of_zero_disables_when_tenant_has_value(
    db: Session, tenant: Tenant, shop: Shop
) -> None:
    tenant.auto_resolve_shortage_cents = 5000
    shop.auto_resolve_shortage_cents_override = 0
    seed_tenant_system_user(db, tenant.id)
    db.flush()
    shift = _make_shift(db, tenant, shop, discrepancy=-100)

    assert maybe_auto_resolve_shift(db, shift, tenant, shop) is False


def test_shop_override_null_falls_back_to_tenant(db: Session, tenant: Tenant, shop: Shop) -> None:
    tenant.auto_resolve_shortage_cents = 5000
    shop.auto_resolve_shortage_cents_override = None
    seed_tenant_system_user(db, tenant.id)
    db.flush()
    shift = _make_shift(db, tenant, shop, discrepancy=-100)

    assert maybe_auto_resolve_shift(db, shift, tenant, shop) is True


def test_raises_if_system_user_missing(db: Session, tenant: Tenant, shop: Shop) -> None:
    tenant.auto_resolve_shortage_cents = 5000
    db.flush()  # do NOT seed system user
    shift = _make_shift(db, tenant, shop, discrepancy=-100)

    with pytest.raises(RuntimeError, match="system user"):
        maybe_auto_resolve_shift(db, shift, tenant, shop)
