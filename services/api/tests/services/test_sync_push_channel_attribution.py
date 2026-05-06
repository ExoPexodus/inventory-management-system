import uuid

import pytest

from app.models import Channel, Customer, CustomerChannel, InventoryPool, InventoryPoolShop, Product, Shop, StockMovement, Tenant, Transaction


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    """Mirror migration auto-create: pool + pool_shop + POS channel for the test shop."""
    pool = InventoryPool(
        tenant_id=tenant.id,
        name=f"POS at {shop.name}",
        fulfillment_policy="fulfill_from_primary",
    )
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id,
        type="pos",
        name=f"POS at {shop.name}",
        status="active",
        config={},
        inventory_pool_id=pool.id,
        currency_code="USD",
        shop_id=shop.id,
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def product(db, tenant: Tenant, shop: Shop) -> Product:
    p = Product(
        tenant_id=tenant.id,
        name="Widget",
        sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=500,
    )
    db.add(p)
    db.flush()
    # Seed positive stock so the sale doesn't go negative (shop_id must match the sale)
    db.add(StockMovement(
        tenant_id=tenant.id,
        shop_id=shop.id,
        product_id=p.id,
        quantity_delta=100,
        movement_type="purchase_receipt",
        idempotency_key=f"seed-{uuid.uuid4().hex}",
    ))
    db.flush()
    return p


def _build_event(shop_id, product_id, **overrides):
    """Build a sale_completed event payload."""
    base = {
        "id": str(uuid.uuid4()),
        "client_mutation_id": f"mut-{uuid.uuid4().hex[:8]}",
        "shop_id": str(shop_id),
        "lines": [
            {"product_id": str(product_id), "quantity": 1, "unit_price_cents": 500},
        ],
        "total_cents": 500,
        "tax_cents": 0,
        "payments": [{"tender_type": "cash", "amount_cents": 500}],
    }
    base.update(overrides)
    return base


def test_pos_sale_attributes_to_pos_channel(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product) -> None:
    from app.services.sync_push import apply_sale_completed

    event = _build_event(shop.id, product.id)
    apply_sale_completed(db, tenant_id=tenant.id, device_id=None, allowed_shop_ids=[shop.id], event=event)
    db.flush()

    from sqlalchemy import select
    txn = db.execute(
        select(Transaction).where(Transaction.client_mutation_id == event["client_mutation_id"])
    ).scalar_one()
    assert txn.source_channel_id == channel.id

    movements = db.execute(
        select(StockMovement).where(StockMovement.transaction_id == txn.id)
    ).scalars().all()
    assert len(movements) >= 1
    for m in movements:
        assert m.source_channel_id == channel.id


def test_pos_sale_with_email_creates_customer_attribution(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product) -> None:
    from app.services.sync_push import apply_sale_completed

    event = _build_event(
        shop.id, product.id,
        customer_email="walkin@example.com",
        customer_phone="5555555555",
        customer_name="Walk-in Customer",
    )
    apply_sale_completed(db, tenant_id=tenant.id, device_id=None, allowed_shop_ids=[shop.id], event=event)
    db.flush()

    from sqlalchemy import select
    cust = db.execute(
        select(Customer).where(Customer.tenant_id == tenant.id, Customer.email == "walkin@example.com")
    ).scalar_one()
    assert cust.created_via_channel_id == channel.id

    attr = db.execute(
        select(CustomerChannel).where(
            CustomerChannel.customer_id == cust.id,
            CustomerChannel.channel_id == channel.id,
        )
    ).scalar_one()
    assert attr is not None


def test_existing_customer_matched_by_email_during_pos_sale(db, tenant: Tenant, shop: Shop, channel: Channel, product: Product) -> None:
    """An existing customer is matched by email, not duplicated."""
    from app.services.sync_push import apply_sale_completed

    existing = Customer(tenant_id=tenant.id, phone="6666666666", email="returning@example.com", name="Returning")
    db.add(existing)
    db.flush()

    event = _build_event(shop.id, product.id, customer_email="returning@example.com")
    apply_sale_completed(db, tenant_id=tenant.id, device_id=None, allowed_shop_ids=[shop.id], event=event)
    db.flush()

    from sqlalchemy import select
    matches = db.execute(
        select(Customer).where(
            Customer.tenant_id == tenant.id,
            Customer.email == "returning@example.com",
        )
    ).scalars().all()
    assert len(matches) == 1, "Expected match-by-email to NOT create a duplicate"
    assert matches[0].id == existing.id
