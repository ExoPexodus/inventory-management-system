import uuid

import pytest

from app.models import Channel, InventoryPool, InventoryPoolShop, Product, Shop, StockMovement, Tenant


@pytest.fixture()
def stocked_product(db, tenant: Tenant, shop: Shop) -> Product:
    """Create a product and seed a stock movement so on_hand > 0."""
    p = Product(
        tenant_id=tenant.id,
        name="Widget",
        sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=500,
    )
    db.add(p)
    db.flush()
    db.add(StockMovement(
        tenant_id=tenant.id,
        shop_id=shop.id,
        product_id=p.id,
        quantity_delta=10,
        movement_type="purchase_receipt",
        idempotency_key=f"seed-{uuid.uuid4().hex}",
    ))
    db.flush()
    return p


@pytest.fixture()
def tenant_default_pool(db, tenant: Tenant, shop: Shop) -> InventoryPool:
    """Create a tenant-wide 'All Shops' pool containing the test shop.
    Mirrors what the migration does for pre-existing tenants."""
    pool = InventoryPool(tenant_id=tenant.id, name="All Shops")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    return pool


@pytest.fixture()
def shop_pos_channel(db, tenant: Tenant, shop: Shop) -> Channel:
    """Create a POS channel + single-shop pool for the test shop."""
    pool = InventoryPool(tenant_id=tenant.id, name=f"POS at {shop.name}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id,
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


def test_default_pool_for_tenant_returns_all_shops_pool(db, tenant: Tenant, tenant_default_pool: InventoryPool) -> None:
    from app.services.inventory_pool_service import default_pool_for_tenant
    pool = default_pool_for_tenant(db, tenant.id)
    assert pool is not None
    assert pool.name == "All Shops"
    assert pool.tenant_id == tenant.id


def test_pool_shops_returns_shop_ids(db, tenant: Tenant, shop: Shop, tenant_default_pool: InventoryPool) -> None:
    from app.services.inventory_pool_service import pool_shops
    shop_ids = pool_shops(db, tenant_default_pool.id)
    assert shop.id in shop_ids


def test_available_stock_for_channel_sums_pool_shops(db, tenant: Tenant, shop: Shop, stocked_product: Product, shop_pos_channel: Channel) -> None:
    """A channel pointing at a single-shop pool sees that shop's stock."""
    from app.services.inventory_pool_service import available_stock_for_channel
    available = available_stock_for_channel(db, shop_pos_channel.id, stocked_product.id)
    assert available == 10


def test_available_stock_with_multi_shop_pool(db, tenant: Tenant) -> None:
    """A pool with two shops returns the sum of stock across both."""
    from app.services.inventory_pool_service import available_stock_for_channel

    shop_a = Shop(tenant_id=tenant.id, name=f"shop-a-{uuid.uuid4().hex[:6]}")
    shop_b = Shop(tenant_id=tenant.id, name=f"shop-b-{uuid.uuid4().hex[:6]}")
    db.add(shop_a)
    db.add(shop_b)
    db.flush()

    product = Product(
        tenant_id=tenant.id,
        name="Gadget",
        sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=500,
    )
    db.add(product)
    db.flush()

    db.add(StockMovement(
        tenant_id=tenant.id, shop_id=shop_a.id, product_id=product.id,
        quantity_delta=4, movement_type="purchase_receipt",
        idempotency_key=f"seed-a-{uuid.uuid4().hex}",
    ))
    db.add(StockMovement(
        tenant_id=tenant.id, shop_id=shop_b.id, product_id=product.id,
        quantity_delta=6, movement_type="purchase_receipt",
        idempotency_key=f"seed-b-{uuid.uuid4().hex}",
    ))
    db.flush()

    pool = InventoryPool(tenant_id=tenant.id, name=f"multi-pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop_a.id))
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop_b.id))
    db.flush()

    channel = Channel(
        tenant_id=tenant.id,
        type="manual",
        name=f"manual-{uuid.uuid4().hex[:6]}",
        config={},
        inventory_pool_id=pool.id,
        currency_code="USD",
    )
    db.add(channel)
    db.flush()

    assert available_stock_for_channel(db, channel.id, product.id) == 10


def test_available_stock_for_unknown_channel_returns_zero(db, tenant: Tenant, stocked_product: Product) -> None:
    from app.services.inventory_pool_service import available_stock_for_channel
    assert available_stock_for_channel(db, uuid.uuid4(), stocked_product.id) == 0
