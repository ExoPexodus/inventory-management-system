import uuid

import pytest

from app.models import Channel, Customer, CustomerChannel, InventoryPool, InventoryPoolShop, Shop, Tenant


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    """Create a POS channel + single-shop pool for the test shop (mirrors migration auto-create)."""
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


def test_match_by_email_returns_existing(db, tenant: Tenant, channel: Channel) -> None:
    from app.services.customer_resolver import resolve_or_create_customer

    existing = Customer(tenant_id=tenant.id, phone="9999999999", email="alice@example.com", name="Alice")
    db.add(existing)
    db.flush()

    resolved = resolve_or_create_customer(
        db, tenant.id, channel.id, email="alice@example.com",
    )
    assert resolved.id == existing.id


def test_match_by_phone_when_email_missing(db, tenant: Tenant, channel: Channel) -> None:
    from app.services.customer_resolver import resolve_or_create_customer

    existing = Customer(tenant_id=tenant.id, phone="9876543210", name="Bob")
    db.add(existing)
    db.flush()

    resolved = resolve_or_create_customer(
        db, tenant.id, channel.id, phone="9876543210",
    )
    assert resolved.id == existing.id


def test_email_takes_precedence_over_phone(db, tenant: Tenant, channel: Channel) -> None:
    from app.services.customer_resolver import resolve_or_create_customer

    by_email = Customer(tenant_id=tenant.id, phone="1111111111", email="charlie@example.com", name="Charlie")
    by_phone = Customer(tenant_id=tenant.id, phone="2222222222", name="Charlie #2")
    db.add(by_email)
    db.add(by_phone)
    db.flush()

    resolved = resolve_or_create_customer(
        db, tenant.id, channel.id,
        email="charlie@example.com",
        phone="2222222222",
    )
    assert resolved.id == by_email.id


def test_creates_new_when_no_match(db, tenant: Tenant, channel: Channel) -> None:
    from app.services.customer_resolver import resolve_or_create_customer

    new = resolve_or_create_customer(
        db, tenant.id, channel.id,
        email="dave@example.com",
        phone="3333333333",
        name="Dave",
    )
    assert new.id is not None
    assert new.email == "dave@example.com"
    assert new.phone == "3333333333"
    assert new.name == "Dave"
    assert new.created_via_channel_id == channel.id


def test_writes_customer_channel_attribution(db, tenant: Tenant, channel: Channel) -> None:
    from sqlalchemy import select
    from app.services.customer_resolver import resolve_or_create_customer

    cust = resolve_or_create_customer(
        db, tenant.id, channel.id, email="erin@example.com", phone="4444444444",
    )
    rows = db.execute(
        select(CustomerChannel).where(
            CustomerChannel.customer_id == cust.id,
            CustomerChannel.channel_id == channel.id,
        )
    ).scalars().all()
    assert len(rows) == 1


def test_attribution_is_idempotent(db, tenant: Tenant, channel: Channel) -> None:
    from sqlalchemy import select
    from app.services.customer_resolver import resolve_or_create_customer

    resolve_or_create_customer(db, tenant.id, channel.id, email="frank@example.com")
    cust = resolve_or_create_customer(db, tenant.id, channel.id, email="frank@example.com")

    rows = db.execute(
        select(CustomerChannel).where(
            CustomerChannel.customer_id == cust.id,
            CustomerChannel.channel_id == channel.id,
        )
    ).scalars().all()
    assert len(rows) == 1


def test_returns_none_when_no_email_no_phone(db, tenant: Tenant, channel: Channel) -> None:
    from app.services.customer_resolver import resolve_or_create_customer
    resolved = resolve_or_create_customer(db, tenant.id, channel.id, name="No Identifier")
    assert resolved is None


def test_email_normalization_is_case_insensitive(db, tenant: Tenant, channel: Channel) -> None:
    from app.services.customer_resolver import resolve_or_create_customer

    cust1 = resolve_or_create_customer(db, tenant.id, channel.id, email="MIXED@case.COM")
    cust2 = resolve_or_create_customer(db, tenant.id, channel.id, email="mixed@case.com")
    assert cust1.id == cust2.id
