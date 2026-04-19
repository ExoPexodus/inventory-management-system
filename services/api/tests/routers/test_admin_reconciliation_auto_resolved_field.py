from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models import ShiftClosing, Shop, Tenant
from app.routers.admin_reconciliation import _rec_status
from app.services.reconciliation_auto_resolve import AUTO_RESOLVED_PREFIX


def _closed_shift(db: Session, tenant: Tenant, shop: Shop, discrepancy: int = -100) -> ShiftClosing:
    shift = ShiftClosing(
        id=uuid4(),
        tenant_id=tenant.id,
        shop_id=shop.id,
        opened_at=datetime.now(UTC) - timedelta(hours=4),
        closed_at=datetime.now(UTC),
        status="closed",
        expected_cash_cents=10000,
        reported_cash_cents=10000 + discrepancy,
        discrepancy_cents=discrepancy,
    )
    db.add(shift)
    db.flush()
    return shift


def test_rec_status_auto_resolved_note_marks_resolved_and_auto(
    db: Session, tenant: Tenant, shop: Shop,
) -> None:
    shift = _closed_shift(db, tenant, shop)
    shift.notes = (
        f"\n{AUTO_RESOLVED_PREFIX} by system+x@internal.ims on 2026-04-19T00:00:00Z] "
        "Variance -100 within tenant shortage threshold of 5000."
    )

    status, note, auto = _rec_status(shift)
    assert status == "resolved"
    assert note is not None and AUTO_RESOLVED_PREFIX in note
    assert auto is True


def test_rec_status_manual_resolved_note_is_resolved_not_auto(
    db: Session, tenant: Tenant, shop: Shop,
) -> None:
    shift = _closed_shift(db, tenant, shop)
    shift.notes = "\n[RESOLVED by admin@example.com on 2026-04-19T00:00:00Z]: counted twice."

    status, note, auto = _rec_status(shift)
    assert status == "resolved"
    assert note is not None
    assert auto is False


def test_rec_status_unresolved_variance_is_variance_not_auto(
    db: Session, tenant: Tenant, shop: Shop,
) -> None:
    shift = _closed_shift(db, tenant, shop, discrepancy=-500)
    shift.notes = None

    status, note, auto = _rec_status(shift)
    assert status == "variance"
    assert note is None
    assert auto is False


def test_rec_status_zero_variance_pending_review_not_auto(
    db: Session, tenant: Tenant, shop: Shop,
) -> None:
    shift = _closed_shift(db, tenant, shop, discrepancy=0)
    shift.notes = None
    shift.reviewed_by_user_id = None

    status, note, auto = _rec_status(shift)
    assert status == "pending_review"
    assert auto is False


def test_rec_status_zero_variance_reviewed_is_matched_not_auto(
    db: Session, tenant: Tenant, shop: Shop,
) -> None:
    shift = _closed_shift(db, tenant, shop, discrepancy=0)
    shift.notes = None
    shift.reviewed_by_user_id = uuid4()

    status, note, auto = _rec_status(shift)
    assert status == "matched"
    assert auto is False
