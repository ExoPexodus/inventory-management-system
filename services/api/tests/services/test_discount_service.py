import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models import Channel, Customer, Discount, DiscountUse, InventoryPool, InventoryPoolShop, Shop, Tenant


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="headless", name=f"headless-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="INR",
    )
    db.add(ch)
    db.flush()
    return ch


def _discount(db, tenant, **kwargs) -> Discount:
    d = Discount(tenant_id=tenant.id, **kwargs)
    db.add(d)
    db.flush()
    return d


def test_percentage_discount_applied(db, tenant: Tenant, channel: Channel) -> None:
    disc = _discount(db, tenant, name="20% off", code="TWENTY", discount_type="percentage",
                     value_bps=2000, status="active")

    from app.services.discount_service import apply_discount
    result = apply_discount(db, tenant_id=tenant.id, channel_id=channel.id,
                            code="TWENTY", cart_subtotal_cents=10000)
    assert result["discount_amount_cents"] == 2000
    assert result["final_total_cents"] == 8000
    assert result["is_free_shipping"] is False
    assert result["discount_id"] == disc.id


def test_fixed_amount_discount(db, tenant: Tenant, channel: Channel) -> None:
    _discount(db, tenant, name="₹500 off", code="FLAT500", discount_type="fixed_amount",
              value_cents=500, status="active")

    from app.services.discount_service import apply_discount
    result = apply_discount(db, tenant_id=tenant.id, channel_id=channel.id,
                            code="FLAT500", cart_subtotal_cents=3000)
    assert result["discount_amount_cents"] == 500
    assert result["final_total_cents"] == 2500


def test_fixed_amount_capped_at_cart_total(db, tenant: Tenant, channel: Channel) -> None:
    _discount(db, tenant, name="₹2000 off", code="BIG2000", discount_type="fixed_amount",
              value_cents=2000, status="active")

    from app.services.discount_service import apply_discount
    result = apply_discount(db, tenant_id=tenant.id, channel_id=channel.id,
                            code="BIG2000", cart_subtotal_cents=1500)
    assert result["discount_amount_cents"] == 1500
    assert result["final_total_cents"] == 0


def test_free_shipping_discount(db, tenant: Tenant, channel: Channel) -> None:
    _discount(db, tenant, name="Free Ship", code="FREESHIP", discount_type="free_shipping",
              status="active")

    from app.services.discount_service import apply_discount
    result = apply_discount(db, tenant_id=tenant.id, channel_id=channel.id,
                            code="FREESHIP", cart_subtotal_cents=5000)
    assert result["discount_amount_cents"] == 0
    assert result["final_total_cents"] == 5000
    assert result["is_free_shipping"] is True


def test_expired_code_rejected(db, tenant: Tenant, channel: Channel) -> None:
    from app.services.discount_service import DiscountNotEligibleError
    _discount(db, tenant, name="Expired", code="OLD", discount_type="percentage",
              value_bps=1000, status="active",
              expires_at=datetime.now(UTC) - timedelta(days=1))

    with pytest.raises(DiscountNotEligibleError, match="expired"):
        from app.services.discount_service import apply_discount
        apply_discount(db, tenant_id=tenant.id, channel_id=channel.id,
                      code="OLD", cart_subtotal_cents=5000)


def test_not_started_code_rejected(db, tenant: Tenant, channel: Channel) -> None:
    from app.services.discount_service import DiscountNotEligibleError
    _discount(db, tenant, name="Future", code="SOON", discount_type="percentage",
              value_bps=500, status="active",
              starts_at=datetime.now(UTC) + timedelta(days=5))

    with pytest.raises(DiscountNotEligibleError, match="not yet"):
        from app.services.discount_service import apply_discount
        apply_discount(db, tenant_id=tenant.id, channel_id=channel.id,
                      code="SOON", cart_subtotal_cents=5000)


def test_min_subtotal_condition_enforced(db, tenant: Tenant, channel: Channel) -> None:
    from app.services.discount_service import DiscountNotEligibleError
    _discount(db, tenant, name="Min 1000", code="MIN1000", discount_type="percentage",
              value_bps=1000, status="active", min_subtotal_cents=10000)

    with pytest.raises(DiscountNotEligibleError, match="minimum"):
        from app.services.discount_service import apply_discount
        apply_discount(db, tenant_id=tenant.id, channel_id=channel.id,
                      code="MIN1000", cart_subtotal_cents=5000)


def test_global_usage_limit_enforced(db, tenant: Tenant, channel: Channel) -> None:
    from app.services.discount_service import DiscountNotEligibleError
    disc = _discount(db, tenant, name="Limited", code="LTD", discount_type="percentage",
                     value_bps=500, status="active", max_uses_total=2)
    for _ in range(2):
        db.add(DiscountUse(tenant_id=tenant.id, discount_id=disc.id, discount_amount_cents=50))
    db.flush()

    with pytest.raises(DiscountNotEligibleError, match="usage limit"):
        from app.services.discount_service import apply_discount
        apply_discount(db, tenant_id=tenant.id, channel_id=channel.id,
                      code="LTD", cart_subtotal_cents=1000)


def test_per_customer_limit_enforced(db, tenant: Tenant, channel: Channel) -> None:
    from app.services.discount_service import DiscountNotEligibleError
    customer = Customer(tenant_id=tenant.id, phone=f"+1{uuid.uuid4().hex[:10]}")
    db.add(customer)
    db.flush()
    customer_id = customer.id
    disc = _discount(db, tenant, name="Once per customer", code="ONCE", discount_type="percentage",
                     value_bps=500, status="active", max_uses_per_customer=1)
    db.add(DiscountUse(tenant_id=tenant.id, discount_id=disc.id,
                       customer_id=customer_id, discount_amount_cents=50))
    db.flush()

    with pytest.raises(DiscountNotEligibleError, match="customer"):
        from app.services.discount_service import apply_discount
        apply_discount(db, tenant_id=tenant.id, channel_id=channel.id,
                      code="ONCE", cart_subtotal_cents=1000, customer_id=customer_id)


def test_unknown_code_raises(db, tenant: Tenant, channel: Channel) -> None:
    from app.services.discount_service import DiscountNotFoundError
    with pytest.raises(DiscountNotFoundError):
        from app.services.discount_service import apply_discount
        apply_discount(db, tenant_id=tenant.id, channel_id=channel.id,
                      code="DOESNOTEXIST", cart_subtotal_cents=1000)


def test_automatic_discount_found_without_code(db, tenant: Tenant, channel: Channel) -> None:
    _discount(db, tenant, name="Always 5% off", code=None, discount_type="percentage",
              value_bps=500, status="active")

    from app.services.discount_service import apply_discount
    result = apply_discount(db, tenant_id=tenant.id, channel_id=channel.id,
                            code=None, cart_subtotal_cents=10000)
    assert result["discount_amount_cents"] == 500


def test_paused_discount_not_applied(db, tenant: Tenant, channel: Channel) -> None:
    from app.services.discount_service import DiscountNotFoundError
    _discount(db, tenant, name="Paused", code="PAUSED", discount_type="percentage",
              value_bps=1000, status="paused")
    with pytest.raises(DiscountNotFoundError):
        from app.services.discount_service import apply_discount
        apply_discount(db, tenant_id=tenant.id, channel_id=channel.id,
                      code="PAUSED", cart_subtotal_cents=5000)
