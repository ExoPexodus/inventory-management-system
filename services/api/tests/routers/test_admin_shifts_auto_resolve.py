from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminContext
from app.models import PaymentAllocation, ShiftClosing, Shop, Tenant, Transaction
from app.routers.admin_shifts import CloseShiftBody, close_shift
from app.services.reconciliation_auto_resolve import AUTO_RESOLVED_PREFIX
from app.services.tenant_system_user import seed_tenant_system_user


def _ctx(tenant_id, user_id=None):
    return AdminContext(
        user_id=user_id,
        tenant_id=tenant_id,
        role="admin",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset(),
    )


def _seed_cash_payment(
    db: Session, tenant: Tenant, shop: Shop, opened_at: datetime, amount_cents: int
) -> None:
    """Insert a posted cash payment inside the shift window to push expected_cash_cents up."""
    txn = Transaction(
        id=uuid4(),
        tenant_id=tenant.id,
        shop_id=shop.id,
        total_cents=amount_cents,
        status="posted",
        client_mutation_id=uuid4().hex,
        created_at=opened_at + timedelta(minutes=30),
    )
    db.add(txn)
    db.flush()
    alloc = PaymentAllocation(
        id=uuid4(),
        transaction_id=txn.id,
        tender_type="cash",
        amount_cents=amount_cents,
    )
    db.add(alloc)
    db.flush()


@pytest.fixture
def open_shift(db: Session, tenant: Tenant, shop: Shop) -> ShiftClosing:
    opened_at = datetime.now(UTC) - timedelta(hours=4)
    shift = ShiftClosing(
        id=uuid4(),
        tenant_id=tenant.id,
        shop_id=shop.id,
        opened_at=opened_at,
        status="open",
        expected_cash_cents=0,
        reported_cash_cents=0,
        discrepancy_cents=0,
    )
    db.add(shift)
    db.commit()
    db.refresh(shift)
    return shift


def test_admin_close_shift_auto_resolves_small_shortage(
    db: Session, tenant: Tenant, shop: Shop, open_shift: ShiftClosing,
) -> None:
    """When discrepancy is within threshold, AUTO_RESOLVED_PREFIX should appear in notes."""
    _seed_cash_payment(db, tenant, shop, open_shift.opened_at, 10000)
    db.commit()

    tenant.auto_resolve_shortage_cents = 5000
    seed_tenant_system_user(db, tenant.id)
    db.commit()

    # expected = 10000, reported = 7000  =>  discrepancy = -3000  (shortage within 5000 threshold)
    close_shift(
        shift_id=open_shift.id,
        body=CloseShiftBody(reported_cash_cents=7000),
        ctx=_ctx(tenant.id),
        db=db,
    )

    db.refresh(open_shift)
    assert open_shift.discrepancy_cents == -3000
    assert AUTO_RESOLVED_PREFIX in (open_shift.notes or "")


def test_admin_close_shift_does_not_auto_resolve_over_threshold(
    db: Session, tenant: Tenant, shop: Shop, open_shift: ShiftClosing,
) -> None:
    """When discrepancy exceeds threshold, notes should NOT contain AUTO_RESOLVED_PREFIX."""
    _seed_cash_payment(db, tenant, shop, open_shift.opened_at, 10000)
    db.commit()

    tenant.auto_resolve_shortage_cents = 1000
    seed_tenant_system_user(db, tenant.id)
    db.commit()

    # expected = 10000, reported = 5000  =>  discrepancy = -5000  (shortage over 1000 threshold)
    close_shift(
        shift_id=open_shift.id,
        body=CloseShiftBody(reported_cash_cents=5000),
        ctx=_ctx(tenant.id),
        db=db,
    )

    db.refresh(open_shift)
    assert open_shift.discrepancy_cents == -5000
    assert AUTO_RESOLVED_PREFIX not in (open_shift.notes or "")
