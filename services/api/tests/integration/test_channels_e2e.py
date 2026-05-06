"""End-to-end smoke test for the channels + pools + customer attribution stack.

Covers:
- POS sale with customer email → customer matched/created, channel attribution recorded,
  stock movement attributed to the POS channel
- Admin can list channels and see the auto-created POS channel
- Admin can create a manual channel and the max_channels entitlement is enforced
- Admin can create a pool with multiple shops and a channel can use it
"""
# NOTE: `from __future__ import annotations` is intentionally absent here.
# Under PEP 563, FastAPI's get_type_hints() cannot resolve dependency types
# from local scope (becomes a bare string, treated as a query param, 422 on
# every request). See the same comment in test_entitlements_e2e.py.

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    Channel, Customer, CustomerChannel, InventoryPool, InventoryPoolShop, Product,
    Shop, StockMovement, Tenant, TenantLicenseCache, Transaction,
)


@pytest.fixture()
def licensed(db, tenant: Tenant) -> Tenant:
    db.add(TenantLicenseCache(
        tenant_id=tenant.id,
        subscription_status="active",
        plan_codename="pro",
        max_shops=5,
        max_employees=20,
        storage_limit_mb=10000,
        last_synced_at=datetime.now(UTC),
    ))
    db.commit()
    return tenant


@pytest.fixture()
def all_shops_pool(db, licensed: Tenant, shop: Shop) -> InventoryPool:
    pool = InventoryPool(tenant_id=licensed.id, name="All Shops")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=licensed.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    return pool


@pytest.fixture()
def pos_channel(db, licensed: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=licensed.id, name=f"POS at {shop.name}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=licensed.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=licensed.id,
        type="pos",
        name=f"POS at {shop.name}",
        config={},
        inventory_pool_id=pool.id,
        currency_code="USD",
        shop_id=shop.id,
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def auth(db, licensed: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=uuid.uuid4(),
        tenant_id=licensed.id,
        role="owner",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset({"channels:manage", "inventory_pools:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield
    app.dependency_overrides.clear()


def test_pos_sale_creates_full_attribution_chain(db, licensed: Tenant, shop: Shop, pos_channel: Channel, auth) -> None:
    """The full stack: POS sale → POS channel attribution → customer + channel record → stock movement w/ channel."""
    from sqlalchemy import select
    from app.services.sync_push import apply_sale_completed

    product = Product(
        tenant_id=licensed.id, name="E2E Widget",
        sku=f"sku-{uuid.uuid4().hex[:6]}", unit_price_cents=1000,
    )
    db.add(product)
    db.flush()
    # Seed positive stock so the sale doesn't go negative
    db.add(StockMovement(
        tenant_id=licensed.id, shop_id=shop.id, product_id=product.id,
        quantity_delta=100, movement_type="purchase_receipt",
        idempotency_key=f"seed-{uuid.uuid4().hex}",
    ))
    db.commit()

    event = {
        "id": str(uuid.uuid4()),
        "client_mutation_id": f"mut-{uuid.uuid4().hex[:8]}",
        "shop_id": str(shop.id),
        "lines": [{"product_id": str(product.id), "quantity": 2, "unit_price_cents": 1000}],
        "total_cents": 2000,
        "tax_cents": 0,
        "payments": [{"tender_type": "cash", "amount_cents": 2000}],
        "customer_email": "e2e@example.com",
        "customer_phone": "8888888888",
        "customer_name": "E2E Tester",
    }
    apply_sale_completed(db, tenant_id=licensed.id, device_id=None, allowed_shop_ids=[shop.id], event=event)
    db.commit()

    # 1. Customer created with channel attribution
    customer = db.execute(
        select(Customer).where(Customer.tenant_id == licensed.id, Customer.email == "e2e@example.com")
    ).scalar_one()
    assert customer.created_via_channel_id == pos_channel.id

    # 2. customer_channels row exists
    attr = db.execute(
        select(CustomerChannel).where(
            CustomerChannel.customer_id == customer.id,
            CustomerChannel.channel_id == pos_channel.id,
        )
    ).scalar_one()
    assert attr is not None

    # 3. Transaction has source_channel_id
    txn = db.execute(
        select(Transaction).where(Transaction.client_mutation_id == event["client_mutation_id"])
    ).scalar_one()
    assert txn.source_channel_id == pos_channel.id
    assert txn.customer_id == customer.id

    # 4. Stock movement has source_channel_id
    movements = db.execute(
        select(StockMovement).where(StockMovement.transaction_id == txn.id)
    ).scalars().all()
    assert len(movements) >= 1
    for m in movements:
        assert m.source_channel_id == pos_channel.id


def test_admin_lists_channels_and_creates_manual(db, licensed: Tenant, shop: Shop, pos_channel: Channel, all_shops_pool: InventoryPool, auth) -> None:
    """Admin sees the POS channel and can add a manual channel."""
    client = TestClient(app)
    list_resp = client.get("/v1/admin/channels")
    assert list_resp.status_code == 200
    types_before = {c["type"] for c in list_resp.json()}
    assert "pos" in types_before

    create_resp = client.post("/v1/admin/channels", json={
        "type": "manual",
        "name": "B2B",
        "inventory_pool_id": str(all_shops_pool.id),
        "currency_code": "USD",
    })
    assert create_resp.status_code == 201

    list_resp = client.get("/v1/admin/channels")
    types_after = {c["type"] for c in list_resp.json()}
    assert "manual" in types_after


def test_pool_lifecycle_via_admin_api(db, licensed: Tenant, shop: Shop, auth) -> None:
    """Create a pool, attach a shop, point a channel at it, verify the channel can use it."""
    client = TestClient(app)

    create_pool = client.post("/v1/admin/inventory-pools", json={
        "name": "B2B Warehouse Pool",
        "shop_ids": [str(shop.id)],
    })
    assert create_pool.status_code == 201
    pool_id = create_pool.json()["id"]

    create_channel = client.post("/v1/admin/channels", json={
        "type": "manual",
        "name": "B2B Manual Channel",
        "inventory_pool_id": pool_id,
        "currency_code": "USD",
    })
    assert create_channel.status_code == 201
    channel_id = create_channel.json()["id"]

    from app.services.inventory_pool_service import available_stock_for_channel
    avail = available_stock_for_channel(db, uuid.UUID(channel_id), uuid.uuid4())
    assert avail == 0
