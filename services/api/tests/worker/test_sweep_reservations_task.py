import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models import (
    Channel, InventoryPool, InventoryPoolShop, Product, Shop, StockReservation, Tenant,
)


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"POS at {shop.name}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="pos", name=f"POS at {shop.name}", config={},
        inventory_pool_id=pool.id, currency_code="USD", shop_id=shop.id,
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def product(db, tenant: Tenant) -> Product:
    p = Product(tenant_id=tenant.id, name="Widget", sku=f"sku-{uuid.uuid4().hex[:6]}", unit_price_cents=500)
    db.add(p)
    db.flush()
    return p


class _SharedSession:
    """Thin wrapper that routes SessionLocal() calls to the test's db session.

    The conftest wraps every test in a connection-level transaction that is
    rolled back at teardown. db.commit() inside a test only commits within
    that outer transaction — it does NOT make the data visible to a separate
    database connection.  The worker task opens its own SessionLocal(), so it
    would see an empty DB.

    This wrapper makes the task share the test's connection by:
    - forwarding all attribute access to the real session, and
    - converting commit() → flush() so writes stay within the rollback
      envelope (the outer transaction is never committed to disk).
    """

    def __init__(self, session):
        self._session = session

    def commit(self):
        self._session.flush()

    def close(self):
        pass  # don't close the shared test session

    def __getattr__(self, name):
        return getattr(self._session, name)


def test_sweep_task_marks_expired_reservations(
    db, monkeypatch, tenant: Tenant, shop: Shop, channel: Channel, product: Product
) -> None:
    """Calling the worker task wrapper has the same effect as calling sweep_expired directly."""
    expired = StockReservation(
        tenant_id=tenant.id, channel_id=channel.id, product_id=product.id,
        shop_id=shop.id, quantity=1, cart_token="cart_old", purpose="cart",
        status="active", expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db.add(expired)
    db.commit()

    # Patch SessionLocal so the task shares the test's DB connection.
    # The import is inside the task function, so we must patch the source module.
    monkeypatch.setattr("app.db.session.SessionLocal", lambda: _SharedSession(db))

    from app.worker.tasks import sweep_expired_reservations

    result = sweep_expired_reservations()
    assert "swept" in result.lower()

    db.refresh(expired)
    assert expired.status == "expired"


def test_sweep_task_runs_clean_with_no_expired(db, tenant: Tenant) -> None:
    """No expired rows → task returns 0 cleanly."""
    from app.worker.tasks import sweep_expired_reservations
    result = sweep_expired_reservations()
    assert "0" in result or "swept" in result.lower()
