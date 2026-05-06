# Shipping Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a configurable shipping calculator so headless storefronts and hosted checkout can present real shipping rates to shoppers — based on destination, cart weight, cart total, and per-product shipping class.

**Architecture:** Two new tables — `shipping_zones` (a named set of countries/states per channel) and `shipping_rates` (one rate per zone with name, base price, optional conditions, free-shipping threshold, and shipping-class filter). A pure-function `shipping_service.py` runs the calculator: for a given (channel, destination, cart), it finds matching zones → filters to eligible rates → applies currency conversion via the FX engine → returns displayable rate options. A public `POST /v1/shipping/calculate` endpoint exposes the calculator to headless frontends and hosted checkout. Admin CRUD for zones and rates lives in a new `admin_shipping.py` router. Shopify/WooCommerce channels use their own native shipping; only `headless` and `manual` channels consume this engine.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, PostgreSQL (with RLS), pytest

**Out of scope (deferred):**
- Sub-postal-code zone rules (street-level targeting). Countries + states are enough for Phase 0.
- Tiered/per-kg rate bands. Each rate row is one option; multiple rows per zone = multiple options the shopper picks from.
- Carrier integration (UPS, FedEx, India Post API, etc.) — rates are manually configured for now.
- Per-product dimensional weight. `weight_grams` on Product is used as-is; cubic/dim weight is a later enhancement.

---

### Task 1: Migration + ShippingZone + ShippingRate models + contract test

**Files:**
- Create: `services/api/alembic/versions/20260511000001_shipping_engine.py`
- Modify: `services/api/app/models/tables.py`
- Modify: `services/api/app/models/__init__.py`
- Modify: `services/api/tests/test_admin_console_contracts.py`

- [ ] **Step 1: Write failing contract tests**

Add to `services/api/tests/test_admin_console_contracts.py`:

```python
def test_shipping_zone_out_schema() -> None:
    from app.routers.admin_shipping import ShippingZoneOut

    z = ShippingZoneOut(
        id=uuid4(),
        tenant_id=uuid4(),
        channel_id=uuid4(),
        name="Domestic",
        countries=["IN"],
        is_catch_all=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    d = z.model_dump(mode="json")
    assert d["name"] == "Domestic"
    assert d["countries"] == ["IN"]
    assert d["is_catch_all"] is False


def test_shipping_rate_out_schema() -> None:
    from app.routers.admin_shipping import ShippingRateOut

    r = ShippingRateOut(
        id=uuid4(),
        tenant_id=uuid4(),
        zone_id=uuid4(),
        name="Standard",
        base_price_cents=500,
        currency_code="INR",
        free_above_cents=None,
        condition_type="none",
        condition_min=None,
        condition_max=None,
        applies_to_classes=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    d = r.model_dump(mode="json")
    assert d["name"] == "Standard"
    assert d["base_price_cents"] == 500
    assert d["condition_type"] == "none"
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/test_admin_console_contracts.py $CONTAINER:/app/tests/test_admin_console_contracts.py
docker compose exec api python -m pytest tests/test_admin_console_contracts.py::test_shipping_zone_out_schema tests/test_admin_console_contracts.py::test_shipping_rate_out_schema -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routers.admin_shipping'`. Stays red until Task 3.

- [ ] **Step 3: Add SQLAlchemy models**

In `services/api/app/models/tables.py`, append after `ProductImage`:

```python
class ShippingZone(Base):
    """A named geographic area (set of countries) for a channel, with shipping rates.

    A zone with is_catch_all=True matches any destination not covered by other
    zones in the same channel. At most one catch-all zone is expected per channel
    (not enforced at DB level, but the calculator picks the most-specific zone first).
    """
    __tablename__ = "shipping_zones"
    __table_args__ = (
        UniqueConstraint("tenant_id", "channel_id", "name", name="uq_shipping_zone_channel_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # countries: list of ISO 3166-1 alpha-2 codes e.g. ["IN", "US", "GB"]
    # Empty list or null → is_catch_all should be True
    countries: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    is_catch_all: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ShippingRate(Base):
    """One named rate option inside a shipping zone.

    Multiple rates per zone = shopper picks one (e.g., "Standard $5" vs "Express $12").

    Conditions control eligibility:
      condition_type='none'       — always eligible
      condition_type='by_total'   — cart subtotal in [condition_min, condition_max] cents
      condition_type='by_weight'  — total shippable weight in [condition_min, condition_max] grams
      condition_type='by_items'   — total shippable item count in [condition_min, condition_max]

    Null condition_min = no lower bound. Null condition_max = no upper bound.
    free_above_cents: if cart subtotal >= this, the rate's effective price is 0.
    applies_to_classes: if set, rate only applies when ALL items in cart belong to
        one of these shipping classes (or have shipping_class=None).
        null = applies to any cart.
    """
    __tablename__ = "shipping_rates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    zone_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shipping_zones.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    free_above_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    condition_type: Mapped[str] = mapped_column(
        String(32), default="none", server_default="none", nullable=False
    )
    condition_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    condition_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    applies_to_classes: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 4: Export the models**

In `services/api/app/models/__init__.py`, add `ShippingRate` and `ShippingZone` to BOTH the import block and `__all__` (alphabetical).

- [ ] **Step 5: Write the migration**

Create `services/api/alembic/versions/20260511000001_shipping_engine.py`:

```python
"""Shipping engine: shipping_zones + shipping_rates tables

Revision ID: 20260511000001
Revises: 20260510000001
Create Date: 2026-05-11 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

revision = "20260511000001"
down_revision = "20260510000001"
branch_labels = None
depends_on = None


_RLS_POLICY = """
COALESCE(current_setting('ims.is_admin', true), '') = 'true'
OR (
  NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), '') IS NOT NULL
  AND tenant_id = (NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), ''))::uuid
)
"""


def upgrade() -> None:
    # 1. shipping_zones
    op.create_table(
        "shipping_zones",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("countries", JSONB, nullable=True),
        sa.Column("is_catch_all", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "channel_id", "name",
                            name="uq_shipping_zone_channel_name"),
    )
    op.create_index("ix_shipping_zones_tenant_id", "shipping_zones", ["tenant_id"])
    op.create_index("ix_shipping_zones_channel_id", "shipping_zones", ["channel_id"])

    # 2. shipping_rates
    op.create_table(
        "shipping_rates",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("zone_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("shipping_zones.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("base_price_cents", sa.Integer, nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("free_above_cents", sa.Integer, nullable=True),
        sa.Column("condition_type", sa.String(32), nullable=False, server_default="none"),
        sa.Column("condition_min", sa.Integer, nullable=True),
        sa.Column("condition_max", sa.Integer, nullable=True),
        sa.Column("applies_to_classes", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_shipping_rates_zone_id", "shipping_rates", ["zone_id"])
    op.create_index("ix_shipping_rates_tenant_id", "shipping_rates", ["tenant_id"])

    # 3. Permission seed
    op.execute("""
        INSERT INTO permissions (id, codename, display_name, category, description)
        VALUES (gen_random_uuid(), 'shipping:manage', 'Manage Shipping', 'shipping',
                'Manage shipping zones and rates')
        ON CONFLICT (codename) DO UPDATE SET description = EXCLUDED.description
    """)
    op.execute("""
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r, permissions p
        WHERE r.name = 'owner' AND r.is_system = true
          AND p.codename = 'shipping:manage'
        ON CONFLICT DO NOTHING
    """)

    # 4. RLS on both tables
    for table in ["shipping_zones", "shipping_rates"]:
        op.execute(f"""
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
            CREATE POLICY ims_tenant_isolation ON {table}
            USING ({_RLS_POLICY})
            WITH CHECK ({_RLS_POLICY});
        """)


def downgrade() -> None:
    for table in ["shipping_rates", "shipping_zones"]:
        op.execute(f"DROP POLICY IF EXISTS ims_tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.execute("""
        DELETE FROM role_permissions WHERE permission_id IN (
            SELECT id FROM permissions WHERE codename = 'shipping:manage'
        )
    """)
    op.execute("DELETE FROM permissions WHERE codename = 'shipping:manage'")

    op.drop_index("ix_shipping_rates_tenant_id", table_name="shipping_rates")
    op.drop_index("ix_shipping_rates_zone_id", table_name="shipping_rates")
    op.drop_table("shipping_rates")
    op.drop_index("ix_shipping_zones_channel_id", table_name="shipping_zones")
    op.drop_index("ix_shipping_zones_tenant_id", table_name="shipping_zones")
    op.drop_table("shipping_zones")
```

- [ ] **Step 6: Run migration**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/alembic/versions/20260511000001_shipping_engine.py $CONTAINER:/app/alembic/versions/
docker compose exec api alembic upgrade head
```
Expected: `Running upgrade 20260510000001 -> 20260511000001`

- [ ] **Step 7: Verify**

```bash
docker compose exec postgres psql -U ims -d ims -c "\d shipping_zones"
docker compose exec postgres psql -U ims -d ims -c "\d shipping_rates"
docker compose exec postgres psql -U ims -d ims -c "SELECT codename FROM permissions WHERE codename='shipping:manage'"
```
Expected: both tables described, permission row present.

- [ ] **Step 8: Commit**

```bash
git add services/api/alembic/versions/20260511000001_shipping_engine.py \
        services/api/app/models/tables.py \
        services/api/app/models/__init__.py \
        services/api/tests/test_admin_console_contracts.py
git commit -m "feat(shipping): add shipping_zones + shipping_rates tables"
```

---

### Task 2: Shipping calculator service

**Files:**
- Create: `services/api/app/services/shipping_service.py`
- Create: `services/api/tests/services/test_shipping_service.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/services/test_shipping_service.py`:

```python
import uuid
from decimal import Decimal

import pytest

from app.models import Channel, InventoryPool, InventoryPoolShop, Product, ShippingRate, ShippingZone, Shop, Tenant


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"POS at {shop.name}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="headless", name=f"headless-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="USD",
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def physical_product(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id, name="Widget", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=1000, product_type="physical", weight_grams=500,
        shipping_class="standard",
    )
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def digital_product(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id, name="eBook", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=500, product_type="digital",
    )
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def domestic_zone(db, tenant: Tenant, channel: Channel) -> ShippingZone:
    z = ShippingZone(
        tenant_id=tenant.id, channel_id=channel.id,
        name="Domestic", countries=["IN"], is_catch_all=False,
    )
    db.add(z)
    db.flush()
    return z


def _add_rate(db, zone, *, name, base_price, currency="INR", **kwargs) -> ShippingRate:
    r = ShippingRate(
        tenant_id=zone.tenant_id, zone_id=zone.id,
        name=name, base_price_cents=base_price, currency_code=currency,
        **kwargs,
    )
    db.add(r)
    db.flush()
    return r


def test_returns_matching_zone_rate(db, tenant: Tenant, channel: Channel, domestic_zone: ShippingZone, physical_product: Product) -> None:
    _add_rate(db, domestic_zone, name="Standard", base_price=9900, currency="INR")

    from app.services.shipping_service import calculate_shipping_options
    options = calculate_shipping_options(
        db,
        channel_id=channel.id,
        destination_country="IN",
        cart_lines=[{"product_id": physical_product.id, "quantity": 1, "unit_price_cents": 1000}],
        cart_subtotal_cents=1000,
        currency="INR",
    )
    assert len(options) == 1
    assert options[0]["name"] == "Standard"
    assert options[0]["price_cents"] == 9900
    assert options[0]["is_free"] is False


def test_no_matching_zone_returns_empty(db, tenant: Tenant, channel: Channel, domestic_zone: ShippingZone, physical_product: Product) -> None:
    _add_rate(db, domestic_zone, name="Standard", base_price=9900)

    from app.services.shipping_service import calculate_shipping_options
    # Destination US — zone only covers IN
    options = calculate_shipping_options(
        db, channel_id=channel.id, destination_country="US",
        cart_lines=[{"product_id": physical_product.id, "quantity": 1, "unit_price_cents": 1000}],
        cart_subtotal_cents=1000, currency="INR",
    )
    assert options == []


def test_catch_all_zone_matches_any_country(db, tenant: Tenant, channel: Channel, physical_product: Product) -> None:
    catch_all = ShippingZone(
        tenant_id=tenant.id, channel_id=channel.id,
        name="Rest of World", countries=[], is_catch_all=True,
    )
    db.add(catch_all)
    db.flush()
    _add_rate(db, catch_all, name="International", base_price=49900, currency="INR")

    from app.services.shipping_service import calculate_shipping_options
    options = calculate_shipping_options(
        db, channel_id=channel.id, destination_country="DE",
        cart_lines=[{"product_id": physical_product.id, "quantity": 1, "unit_price_cents": 1000}],
        cart_subtotal_cents=1000, currency="INR",
    )
    assert len(options) == 1
    assert options[0]["name"] == "International"


def test_free_above_threshold(db, tenant: Tenant, channel: Channel, domestic_zone: ShippingZone, physical_product: Product) -> None:
    """Rate becomes free when cart subtotal >= free_above_cents."""
    _add_rate(db, domestic_zone, name="Free Standard", base_price=9900,
              currency="INR", free_above_cents=50000)

    from app.services.shipping_service import calculate_shipping_options
    # Below threshold
    below = calculate_shipping_options(
        db, channel_id=channel.id, destination_country="IN",
        cart_lines=[{"product_id": physical_product.id, "quantity": 1, "unit_price_cents": 1000}],
        cart_subtotal_cents=40000, currency="INR",
    )
    assert below[0]["is_free"] is False
    assert below[0]["price_cents"] == 9900

    # At/above threshold
    above = calculate_shipping_options(
        db, channel_id=channel.id, destination_country="IN",
        cart_lines=[{"product_id": physical_product.id, "quantity": 1, "unit_price_cents": 1000}],
        cart_subtotal_cents=60000, currency="INR",
    )
    assert above[0]["is_free"] is True
    assert above[0]["price_cents"] == 0


def test_condition_by_total_filters_rate(db, tenant: Tenant, channel: Channel, domestic_zone: ShippingZone, physical_product: Product) -> None:
    """A by_total condition: rate only shows for cart total in [5000, 10000]."""
    _add_rate(db, domestic_zone, name="Mid-range rate", base_price=4900, currency="INR",
              condition_type="by_total", condition_min=5000, condition_max=10000)

    from app.services.shipping_service import calculate_shipping_options
    # Cart total 4000 — below minimum
    out_range = calculate_shipping_options(
        db, channel_id=channel.id, destination_country="IN",
        cart_lines=[{"product_id": physical_product.id, "quantity": 1, "unit_price_cents": 1000}],
        cart_subtotal_cents=4000, currency="INR",
    )
    assert out_range == []

    # Cart total 7000 — in range
    in_range = calculate_shipping_options(
        db, channel_id=channel.id, destination_country="IN",
        cart_lines=[{"product_id": physical_product.id, "quantity": 1, "unit_price_cents": 1000}],
        cart_subtotal_cents=7000, currency="INR",
    )
    assert len(in_range) == 1


def test_digital_only_cart_returns_no_rates(db, tenant: Tenant, channel: Channel, domestic_zone: ShippingZone, digital_product: Product) -> None:
    """A cart with only digital/non-shippable products returns no shipping rates."""
    _add_rate(db, domestic_zone, name="Standard", base_price=9900, currency="INR")

    from app.services.shipping_service import calculate_shipping_options
    options = calculate_shipping_options(
        db, channel_id=channel.id, destination_country="IN",
        cart_lines=[{"product_id": digital_product.id, "quantity": 1, "unit_price_cents": 500}],
        cart_subtotal_cents=500, currency="INR",
    )
    assert options == []


def test_shipping_class_filter(db, tenant: Tenant, channel: Channel, domestic_zone: ShippingZone, physical_product: Product) -> None:
    """Rate with applies_to_classes only shows for carts where all shippable items match."""
    # Rate only for 'fragile' items
    _add_rate(db, domestic_zone, name="Fragile Rate", base_price=19900, currency="INR",
              applies_to_classes=["fragile"])
    # Standard rate for all
    _add_rate(db, domestic_zone, name="Standard", base_price=9900, currency="INR")

    # physical_product has shipping_class='standard', not 'fragile'
    from app.services.shipping_service import calculate_shipping_options
    options = calculate_shipping_options(
        db, channel_id=channel.id, destination_country="IN",
        cart_lines=[{"product_id": physical_product.id, "quantity": 1, "unit_price_cents": 1000}],
        cart_subtotal_cents=1000, currency="INR",
    )
    names = {o["name"] for o in options}
    assert "Standard" in names
    assert "Fragile Rate" not in names  # product's class 'standard' not in ['fragile']


def test_rate_price_converted_to_requested_currency(db, tenant: Tenant, channel: Channel, domestic_zone: ShippingZone, physical_product: Product) -> None:
    """If rate is in INR but shopper requests USD, price is FX-converted."""
    from app.billing.fx import set_rate
    from decimal import Decimal
    set_rate(db, tenant.id, "INR", "USD", Decimal("0.012"))
    db.flush()

    _add_rate(db, domestic_zone, name="Standard", base_price=9900, currency="INR")

    from app.services.shipping_service import calculate_shipping_options
    options = calculate_shipping_options(
        db, channel_id=channel.id, destination_country="IN",
        cart_lines=[{"product_id": physical_product.id, "quantity": 1, "unit_price_cents": 1000}],
        cart_subtotal_cents=1000, currency="USD",
    )
    assert len(options) == 1
    # 9900 INR * 0.012 = 118.8 → rounds to 119 USD cents
    assert options[0]["currency_code"] == "USD"
    assert options[0]["price_cents"] == 119
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api python -m pytest tests/services/test_shipping_service.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the shipping service**

Create `services/api/app/services/shipping_service.py`:

```python
"""Shipping calculator service.

``calculate_shipping_options`` is the central function. Given a channel, a
destination country, and a cart, it finds all eligible shipping rates and
returns them as displayable options with prices in the requested currency.

Resolution flow:
1. Find all ShippingZones for the channel that cover the destination country.
   Specific zones (countries list includes the destination) beat catch-all zones.
   If a specific zone matches, catch-all zones are not consulted.
2. For each matching zone, collect ShippingRate rows and apply filters:
   a. Skip rate if the cart contains shippable items and shipping_class filter
      doesn't match those items' classes.
   b. Skip rate if a condition (by_total / by_weight / by_items) is set and
      the cart doesn't satisfy it.
   c. If no shippable items exist, return an empty list immediately.
3. For each eligible rate, check free_above_cents and convert the price to
   the requested currency via app.billing.fx.convert.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.fx import convert
from app.billing.money import Money
from app.models import Channel, Product, ShippingRate, ShippingZone
from app.services.product_type_service import is_shippable


def calculate_shipping_options(
    db: Session,
    *,
    channel_id: UUID,
    destination_country: str,
    cart_lines: list[dict[str, Any]],
    cart_subtotal_cents: int,
    currency: str,
) -> list[dict[str, Any]]:
    """Return displayable shipping options for a cart.

    Each option in the returned list:
        {
            "rate_id": UUID,
            "zone_id": UUID,
            "name": str,
            "price_cents": int,
            "currency_code": str,
            "is_free": bool,
        }

    Returns [] when there are no shippable items or no matching zones/rates.

    Args:
        cart_lines: list of {"product_id": UUID, "quantity": int, "unit_price_cents": int}
        cart_subtotal_cents: pre-discount subtotal for condition checks
        currency: ISO 4217 code — rates are converted to this currency before return
    """
    country = destination_country.upper()

    # Resolve channel to get tenant_id
    channel = db.get(Channel, channel_id)
    if channel is None:
        return []

    # Identify shippable cart lines and compute totals
    shippable_lines = _get_shippable_lines(db, cart_lines)
    if not shippable_lines:
        return []

    total_weight_grams = sum(
        (line["weight_grams"] or 0) * line["quantity"]
        for line in shippable_lines
    )
    total_item_count = sum(line["quantity"] for line in shippable_lines)
    cart_classes = {line["shipping_class"] for line in shippable_lines}

    # Find matching zones — specific zones first, catch-all as fallback
    zones = _find_matching_zones(db, channel_id, country)
    if not zones:
        return []

    # Collect eligible rates across all matching zones
    options: list[dict[str, Any]] = []
    for zone in zones:
        rates = db.execute(
            select(ShippingRate).where(ShippingRate.zone_id == zone.id)
        ).scalars().all()

        for rate in rates:
            if not _rate_matches_classes(rate, cart_classes):
                continue
            if not _rate_condition_met(rate, cart_subtotal_cents, total_weight_grams, total_item_count):
                continue

            effective_cents = _effective_price(rate, cart_subtotal_cents)
            is_free = effective_cents == 0

            # Convert price to requested currency
            if rate.currency_code.upper() == currency.upper():
                final_cents = effective_cents
                final_currency = currency.upper()
            else:
                try:
                    converted = convert(
                        db,
                        channel.tenant_id,
                        Money(effective_cents, rate.currency_code),
                        currency,
                    )
                    final_cents = converted.amount_cents
                    final_currency = converted.currency_code
                except Exception:
                    # FX rate missing — skip this rate rather than error
                    continue

            options.append({
                "rate_id": rate.id,
                "zone_id": zone.id,
                "name": rate.name,
                "price_cents": final_cents,
                "currency_code": final_currency,
                "is_free": is_free,
            })

    return options


def _get_shippable_lines(db: Session, cart_lines: list[dict]) -> list[dict]:
    """Return only lines whose product is a shippable type, enriched with weight/class."""
    result = []
    for line in cart_lines:
        product = db.get(Product, line["product_id"])
        if product is None:
            continue
        if not is_shippable(product.product_type):
            continue
        result.append({
            "product_id": product.id,
            "quantity": line["quantity"],
            "unit_price_cents": line["unit_price_cents"],
            "weight_grams": product.weight_grams,
            "shipping_class": product.shipping_class,
        })
    return result


def _find_matching_zones(db: Session, channel_id: UUID, country: str) -> list[ShippingZone]:
    """Find zones for this channel that cover the destination country.

    Returns specific zones (country in their list) if any exist, else catch-all zones.
    """
    all_zones = db.execute(
        select(ShippingZone).where(ShippingZone.channel_id == channel_id)
    ).scalars().all()

    specific = [
        z for z in all_zones
        if z.countries and country in [c.upper() for c in z.countries]
    ]
    if specific:
        return specific

    catch_alls = [z for z in all_zones if z.is_catch_all]
    return catch_alls


def _rate_matches_classes(rate: ShippingRate, cart_classes: set[str | None]) -> bool:
    """Return True if this rate applies to the cart's set of shipping classes."""
    if rate.applies_to_classes is None:
        return True
    allowed = set(rate.applies_to_classes)
    # All cart classes must be in the allowed set (None class = uncategorised, always allowed)
    for cls in cart_classes:
        if cls is None:
            continue
        if cls not in allowed:
            return False
    return True


def _rate_condition_met(
    rate: ShippingRate,
    cart_subtotal_cents: int,
    total_weight_grams: int,
    total_item_count: int,
) -> bool:
    """Return True if the rate's eligibility condition is satisfied."""
    ct = rate.condition_type
    if ct == "none":
        return True

    if ct == "by_total":
        value = cart_subtotal_cents
    elif ct == "by_weight":
        value = total_weight_grams
    elif ct == "by_items":
        value = total_item_count
    else:
        return True  # unknown condition type = allow

    lo = rate.condition_min
    hi = rate.condition_max
    if lo is not None and value < lo:
        return False
    if hi is not None and value > hi:
        return False
    return True


def _effective_price(rate: ShippingRate, cart_subtotal_cents: int) -> int:
    """Return the effective price in the rate's own currency (may be 0 for free shipping)."""
    if rate.free_above_cents is not None and cart_subtotal_cents >= rate.free_above_cents:
        return 0
    return rate.base_price_cents
```

- [ ] **Step 4: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/services/shipping_service.py $CONTAINER:/app/app/services/shipping_service.py
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api python -m pytest tests/services/test_shipping_service.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/services/shipping_service.py \
        services/api/tests/services/test_shipping_service.py
git commit -m "feat(shipping): add shipping calculator service with zone/rate matching"
```

---

### Task 3: Admin CRUD + public calculate endpoint

**Files:**
- Create: `services/api/app/routers/admin_shipping.py`
- Modify: `services/api/app/main.py`
- Create: `services/api/tests/routers/test_admin_shipping.py`
- Create: `services/api/tests/routers/test_shipping_calculate.py`

- [ ] **Step 1: Write the failing tests**

Create `services/api/tests/routers/test_admin_shipping.py`:

```python
# NOTE: `from __future__ import annotations` deliberately absent.

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, InventoryPool, InventoryPoolShop, ShippingRate, ShippingZone, Shop, Tenant


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"POS at {shop.name}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="headless", name=f"headless-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="USD",
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None,
        tenant_id=tenant.id,
        role="owner",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset({"shipping:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_create_zone(db, tenant: Tenant, channel: Channel, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/shipping/zones", json={
        "channel_id": str(channel.id),
        "name": "Domestic",
        "countries": ["IN"],
        "is_catch_all": False,
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Domestic"
    assert body["countries"] == ["IN"]


def test_list_zones(db, tenant: Tenant, channel: Channel, auth_headers) -> None:
    db.add(ShippingZone(
        tenant_id=tenant.id, channel_id=channel.id,
        name="Zone A", countries=["US"], is_catch_all=False,
    ))
    db.commit()

    client = TestClient(app)
    resp = client.get(f"/v1/admin/shipping/zones?channel_id={channel.id}", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_delete_zone(db, tenant: Tenant, channel: Channel, auth_headers) -> None:
    zone = ShippingZone(
        tenant_id=tenant.id, channel_id=channel.id,
        name="Doomed Zone", countries=["ZZ"], is_catch_all=False,
    )
    db.add(zone)
    db.commit()

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/shipping/zones/{zone.id}", headers=auth_headers)
    assert resp.status_code == 204


def test_create_rate(db, tenant: Tenant, channel: Channel, auth_headers) -> None:
    zone = ShippingZone(
        tenant_id=tenant.id, channel_id=channel.id,
        name="Domestic", countries=["IN"], is_catch_all=False,
    )
    db.add(zone)
    db.commit()

    client = TestClient(app)
    resp = client.post(f"/v1/admin/shipping/zones/{zone.id}/rates", json={
        "name": "Standard",
        "base_price_cents": 9900,
        "currency_code": "INR",
        "free_above_cents": 50000,
        "condition_type": "none",
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Standard"
    assert body["base_price_cents"] == 9900
    assert body["free_above_cents"] == 50000


def test_list_rates(db, tenant: Tenant, channel: Channel, auth_headers) -> None:
    zone = ShippingZone(
        tenant_id=tenant.id, channel_id=channel.id,
        name="Z", countries=["IN"], is_catch_all=False,
    )
    db.add(zone)
    db.flush()
    db.add(ShippingRate(
        tenant_id=tenant.id, zone_id=zone.id,
        name="Express", base_price_cents=19900, currency_code="INR",
    ))
    db.commit()

    client = TestClient(app)
    resp = client.get(f"/v1/admin/shipping/zones/{zone.id}/rates", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_delete_rate(db, tenant: Tenant, channel: Channel, auth_headers) -> None:
    zone = ShippingZone(
        tenant_id=tenant.id, channel_id=channel.id,
        name="ZZ", countries=["IN"], is_catch_all=False,
    )
    db.add(zone)
    db.flush()
    rate = ShippingRate(
        tenant_id=tenant.id, zone_id=zone.id,
        name="Doomed Rate", base_price_cents=100, currency_code="INR",
    )
    db.add(rate)
    db.commit()

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/shipping/zones/{zone.id}/rates/{rate.id}", headers=auth_headers)
    assert resp.status_code == 204


def test_cross_tenant_zone_blocked(db, tenant: Tenant, auth_headers) -> None:
    other = Tenant(name=f"other-{uuid.uuid4().hex[:6]}", slug=f"other-{uuid.uuid4().hex[:8]}")
    db.add(other)
    db.flush()
    other_pool = InventoryPool(tenant_id=other.id, name="pool")
    db.add(other_pool)
    db.flush()
    other_ch = Channel(
        tenant_id=other.id, type="headless", name="other-ch",
        config={}, inventory_pool_id=other_pool.id, currency_code="USD",
    )
    db.add(other_ch)
    db.commit()

    client = TestClient(app)
    resp = client.post("/v1/admin/shipping/zones", json={
        "channel_id": str(other_ch.id),
        "name": "Cross-tenant",
        "countries": ["US"],
    }, headers=auth_headers)
    assert resp.status_code == 400
```

Create `services/api/tests/routers/test_shipping_calculate.py`:

```python
# NOTE: `from __future__ import annotations` deliberately absent.

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, InventoryPool, InventoryPoolShop, Product, ShippingRate, ShippingZone, Shop, Tenant


@pytest.fixture()
def setup(db, tenant: Tenant, shop: Shop):
    """Create a headless channel, a physical product, and a domestic shipping zone+rate."""
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    channel = Channel(
        tenant_id=tenant.id, type="headless", name=f"headless-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="INR",
    )
    db.add(channel)
    db.flush()

    product = Product(
        tenant_id=tenant.id, name="Widget", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=1000, product_type="physical", weight_grams=500,
    )
    db.add(product)
    db.flush()

    zone = ShippingZone(
        tenant_id=tenant.id, channel_id=channel.id,
        name="Domestic", countries=["IN"], is_catch_all=False,
    )
    db.add(zone)
    db.flush()

    rate = ShippingRate(
        tenant_id=tenant.id, zone_id=zone.id,
        name="Standard", base_price_cents=9900, currency_code="INR",
    )
    db.add(rate)
    db.commit()

    return {"channel": channel, "product": product, "rate": rate}


@pytest.fixture()
def auth(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id,
        role="owner", role_id=None, is_legacy_token=True,
        permissions=frozenset(),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield
    app.dependency_overrides.clear()


def test_calculate_returns_rates(db, tenant: Tenant, setup, auth) -> None:
    client = TestClient(app)
    resp = client.post("/v1/shipping/calculate", json={
        "channel_id": str(setup["channel"].id),
        "destination": {"country": "IN"},
        "cart_lines": [
            {"product_id": str(setup["product"].id), "quantity": 1, "unit_price_cents": 1000}
        ],
        "cart_subtotal_cents": 1000,
        "currency": "INR",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["name"] == "Standard"
    assert body[0]["price_cents"] == 9900
    assert body[0]["currency_code"] == "INR"


def test_calculate_no_shippable_items(db, tenant: Tenant, setup, auth) -> None:
    """Cart with a digital product only → empty rates list."""
    digital = Product(
        tenant_id=tenant.id, name="eBook", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=500, product_type="digital",
    )
    db.add(digital)
    db.commit()

    client = TestClient(app)
    resp = client.post("/v1/shipping/calculate", json={
        "channel_id": str(setup["channel"].id),
        "destination": {"country": "IN"},
        "cart_lines": [
            {"product_id": str(digital.id), "quantity": 1, "unit_price_cents": 500}
        ],
        "cart_subtotal_cents": 500,
        "currency": "INR",
    })
    assert resp.status_code == 200
    assert resp.json() == []
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/routers/test_admin_shipping.py $CONTAINER:/app/tests/routers/test_admin_shipping.py
docker cp services/api/tests/routers/test_shipping_calculate.py $CONTAINER:/app/tests/routers/test_shipping_calculate.py
docker compose exec api python -m pytest tests/routers/test_admin_shipping.py tests/routers/test_shipping_calculate.py -v
docker compose exec api rm -f /app/tests/routers/test_admin_shipping.py /app/tests/routers/test_shipping_calculate.py
```
Expected: FAIL — router doesn't exist.

- [ ] **Step 3: Implement the router**

Create `services/api/app/routers/admin_shipping.py`:

```python
"""Admin endpoints for shipping zones + rates, plus the public shipping calculator.

Auth for admin endpoints: requires `shipping:manage` permission.
The calculate endpoint uses the existing admin auth but has no permission gate —
it's consumed by headless frontends and the hosted checkout flow.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Channel, ShippingRate, ShippingZone
from app.services.shipping_service import calculate_shipping_options

router = APIRouter(tags=["Admin Shipping"])

_VALID_CONDITION_TYPES = {"none", "by_total", "by_weight", "by_items"}


# ─────────────────────────────── Schemas ───────────────────────────────

class ShippingZoneIn(BaseModel):
    channel_id: UUID
    name: str = Field(min_length=1, max_length=255)
    countries: list[str] = Field(default_factory=list)
    is_catch_all: bool = False


class ShippingZoneOut(BaseModel):
    id: UUID
    tenant_id: UUID
    channel_id: UUID
    name: str
    countries: list[str] | None
    is_catch_all: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ShippingRateIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    base_price_cents: int = Field(ge=0)
    currency_code: str = Field(min_length=3, max_length=3)
    free_above_cents: int | None = Field(default=None, ge=0)
    condition_type: str = "none"
    condition_min: int | None = Field(default=None, ge=0)
    condition_max: int | None = Field(default=None, ge=0)
    applies_to_classes: list[str] | None = None


class ShippingRateOut(BaseModel):
    id: UUID
    tenant_id: UUID
    zone_id: UUID
    name: str
    base_price_cents: int
    currency_code: str
    free_above_cents: int | None
    condition_type: str
    condition_min: int | None
    condition_max: int | None
    applies_to_classes: list[str] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ShippingCalculateDestination(BaseModel):
    country: str = Field(min_length=2, max_length=2)


class ShippingCalculateLineIn(BaseModel):
    product_id: UUID
    quantity: int = Field(ge=1)
    unit_price_cents: int = Field(ge=0)


class ShippingCalculateIn(BaseModel):
    channel_id: UUID
    destination: ShippingCalculateDestination
    cart_lines: list[ShippingCalculateLineIn]
    cart_subtotal_cents: int = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)


class ShippingOptionOut(BaseModel):
    rate_id: UUID
    zone_id: UUID
    name: str
    price_cents: int
    currency_code: str
    is_free: bool


# ─────────────────────────────── Helpers ───────────────────────────────

def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator not assigned to a tenant",
        )
    return ctx.tenant_id


def _get_zone_or_404(db: Session, zone_id: UUID, tenant_id: UUID) -> ShippingZone:
    zone = db.get(ShippingZone, zone_id)
    if zone is None or zone.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Zone not found")
    return zone


# ─────────────────────────────── Zones ───────────────────────────────

@router.get(
    "/v1/admin/shipping/zones",
    response_model=list[ShippingZoneOut],
    dependencies=[require_permission("shipping:manage")],
)
def list_zones(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    channel_id: UUID | None = Query(default=None),
) -> list[ShippingZone]:
    tenant_id = _require_tenant(ctx)
    q = select(ShippingZone).where(ShippingZone.tenant_id == tenant_id)
    if channel_id:
        q = q.where(ShippingZone.channel_id == channel_id)
    q = q.order_by(ShippingZone.name)
    return list(db.execute(q).scalars().all())


@router.post(
    "/v1/admin/shipping/zones",
    response_model=ShippingZoneOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("shipping:manage")],
)
def create_zone(
    body: ShippingZoneIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ShippingZone:
    tenant_id = _require_tenant(ctx)

    # Verify channel belongs to this tenant
    ch = db.get(Channel, body.channel_id)
    if ch is None or ch.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="channel_id does not belong to this tenant",
        )

    zone = ShippingZone(
        tenant_id=tenant_id,
        channel_id=body.channel_id,
        name=body.name,
        countries=[c.upper() for c in body.countries],
        is_catch_all=body.is_catch_all,
    )
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return zone


@router.delete(
    "/v1/admin/shipping/zones/{zone_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("shipping:manage")],
)
def delete_zone(
    zone_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    zone = _get_zone_or_404(db, zone_id, tenant_id)
    db.delete(zone)
    db.commit()


# ─────────────────────────────── Rates ───────────────────────────────

@router.get(
    "/v1/admin/shipping/zones/{zone_id}/rates",
    response_model=list[ShippingRateOut],
    dependencies=[require_permission("shipping:manage")],
)
def list_rates(
    zone_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[ShippingRate]:
    tenant_id = _require_tenant(ctx)
    _get_zone_or_404(db, zone_id, tenant_id)
    rows = db.execute(
        select(ShippingRate).where(ShippingRate.zone_id == zone_id).order_by(ShippingRate.name)
    ).scalars().all()
    return list(rows)


@router.post(
    "/v1/admin/shipping/zones/{zone_id}/rates",
    response_model=ShippingRateOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("shipping:manage")],
)
def create_rate(
    zone_id: UUID,
    body: ShippingRateIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ShippingRate:
    tenant_id = _require_tenant(ctx)
    zone = _get_zone_or_404(db, zone_id, tenant_id)

    if body.condition_type not in _VALID_CONDITION_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid condition_type. Allowed: {sorted(_VALID_CONDITION_TYPES)}",
        )

    rate = ShippingRate(
        tenant_id=tenant_id,
        zone_id=zone.id,
        name=body.name,
        base_price_cents=body.base_price_cents,
        currency_code=body.currency_code.upper(),
        free_above_cents=body.free_above_cents,
        condition_type=body.condition_type,
        condition_min=body.condition_min,
        condition_max=body.condition_max,
        applies_to_classes=body.applies_to_classes,
    )
    db.add(rate)
    db.commit()
    db.refresh(rate)
    return rate


@router.delete(
    "/v1/admin/shipping/zones/{zone_id}/rates/{rate_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("shipping:manage")],
)
def delete_rate(
    zone_id: UUID,
    rate_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    _get_zone_or_404(db, zone_id, tenant_id)
    rate = db.get(ShippingRate, rate_id)
    if rate is None or rate.zone_id != zone_id or rate.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rate not found")
    db.delete(rate)
    db.commit()


# ─────────────────────────────── Calculate ───────────────────────────────

@router.post("/v1/shipping/calculate", response_model=list[ShippingOptionOut])
def calculate(
    body: ShippingCalculateIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[dict[str, Any]]:
    """Public shipping calculator. Returns available rates for a cart and destination.

    Consumed by headless storefronts and hosted checkout. No permission gate —
    channel_id implicitly scopes the tenant.
    """
    options = calculate_shipping_options(
        db,
        channel_id=body.channel_id,
        destination_country=body.destination.country,
        cart_lines=[line.model_dump() for line in body.cart_lines],
        cart_subtotal_cents=body.cart_subtotal_cents,
        currency=body.currency,
    )
    return options
```

- [ ] **Step 4: Mount the router**

In `services/api/app/main.py`, add `admin_shipping` to the imports and include block (alphabetically).

- [ ] **Step 5: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/main.py $CONTAINER:/app/app/main.py
docker cp services/api/app/routers/admin_shipping.py $CONTAINER:/app/app/routers/admin_shipping.py
docker cp services/api/app/services/shipping_service.py $CONTAINER:/app/app/services/shipping_service.py
docker cp services/api/tests $CONTAINER:/app/tests
docker compose restart api
sleep 5
docker compose exec api python -m pytest \
  tests/routers/test_admin_shipping.py \
  tests/routers/test_shipping_calculate.py \
  tests/test_admin_console_contracts.py::test_shipping_zone_out_schema \
  tests/test_admin_console_contracts.py::test_shipping_rate_out_schema \
  -v
docker compose exec api rm -rf /app/tests
```
Expected: 7 admin tests + 2 calculate tests + 2 contract tests = 11 passed.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/routers/admin_shipping.py \
        services/api/app/main.py \
        services/api/tests/routers/test_admin_shipping.py \
        services/api/tests/routers/test_shipping_calculate.py
git commit -m "feat(shipping): admin CRUD for zones/rates + POST /v1/shipping/calculate"
```

---

### Task 4: Integration smoke test

**Files:**
- Create: `services/api/tests/integration/test_shipping_e2e.py`

- [ ] **Step 1: Write the integration test**

Create `services/api/tests/integration/test_shipping_e2e.py`:

```python
"""End-to-end smoke test for the shipping engine.

Covers:
- Create zone + rate via admin API → calculator returns it for a matching cart
- Free-shipping threshold via the public calculate endpoint
- Digital-only cart → no rates
- Catch-all zone catches unmatched destination
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, InventoryPool, InventoryPoolShop, Product, Shop, Tenant


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


@pytest.fixture()
def physical_product(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id, name="Widget", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=1000, product_type="physical", weight_grams=300,
    )
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def digital_product(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id, name="eBook", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=500, product_type="digital",
    )
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def auth(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id,
        role="owner", role_id=None, is_legacy_token=False,
        permissions=frozenset({"shipping:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield
    app.dependency_overrides.clear()


def _calc(client, channel_id, product_id, qty=1, subtotal=1000, country="IN", currency="INR"):
    return client.post("/v1/shipping/calculate", json={
        "channel_id": str(channel_id),
        "destination": {"country": country},
        "cart_lines": [{"product_id": str(product_id), "quantity": qty, "unit_price_cents": 1000}],
        "cart_subtotal_cents": subtotal,
        "currency": currency,
    })


def test_full_lifecycle(db, tenant: Tenant, channel: Channel, physical_product: Product, auth) -> None:
    """Create zone+rate via admin API → calculator returns the rate for a matching cart."""
    client = TestClient(app)

    # Create zone
    zone_resp = client.post("/v1/admin/shipping/zones", json={
        "channel_id": str(channel.id),
        "name": "India",
        "countries": ["IN"],
    })
    assert zone_resp.status_code == 201
    zone_id = zone_resp.json()["id"]

    # Create rate
    rate_resp = client.post(f"/v1/admin/shipping/zones/{zone_id}/rates", json={
        "name": "Standard",
        "base_price_cents": 9900,
        "currency_code": "INR",
        "free_above_cents": 100000,
    })
    assert rate_resp.status_code == 201

    # Calculate for a cart that doesn't hit the free threshold
    calc = _calc(client, channel.id, physical_product.id, subtotal=1000)
    assert calc.status_code == 200
    options = calc.json()
    assert len(options) == 1
    assert options[0]["name"] == "Standard"
    assert options[0]["price_cents"] == 9900
    assert options[0]["is_free"] is False

    # Calculate for a cart above the free threshold
    free_calc = _calc(client, channel.id, physical_product.id, subtotal=120000)
    assert free_calc.status_code == 200
    free_options = free_calc.json()
    assert free_options[0]["is_free"] is True
    assert free_options[0]["price_cents"] == 0


def test_digital_cart_returns_no_rates(db, tenant: Tenant, channel: Channel, digital_product: Product, auth) -> None:
    """Digital-only cart gets no rates even when a shipping zone/rate exists."""
    client = TestClient(app)

    zone_resp = client.post("/v1/admin/shipping/zones", json={
        "channel_id": str(channel.id), "name": "Everywhere",
        "countries": [], "is_catch_all": True,
    })
    client.post(f"/v1/admin/shipping/zones/{zone_resp.json()['id']}/rates", json={
        "name": "Standard", "base_price_cents": 100, "currency_code": "INR",
    })

    calc = _calc(client, channel.id, digital_product.id, country="IN")
    assert calc.status_code == 200
    assert calc.json() == []


def test_catch_all_serves_unmatched_country(db, tenant: Tenant, channel: Channel, physical_product: Product, auth) -> None:
    """Catch-all zone serves destinations not covered by specific zones."""
    client = TestClient(app)

    zone_resp = client.post("/v1/admin/shipping/zones", json={
        "channel_id": str(channel.id), "name": "Rest of World",
        "countries": [], "is_catch_all": True,
    })
    client.post(f"/v1/admin/shipping/zones/{zone_resp.json()['id']}/rates", json={
        "name": "International", "base_price_cents": 49900, "currency_code": "INR",
    })

    calc = _calc(client, channel.id, physical_product.id, country="DE")
    assert calc.status_code == 200
    options = calc.json()
    assert len(options) == 1
    assert options[0]["name"] == "International"
    assert options[0]["price_cents"] == 49900
```

- [ ] **Step 2: Run integration test**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest tests/integration/test_shipping_e2e.py -v
docker compose exec api rm -rf /app/tests
```
Expected: 3 passed.

- [ ] **Step 3: Run the full shipping suite**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest \
  tests/services/test_shipping_service.py \
  tests/routers/test_admin_shipping.py \
  tests/routers/test_shipping_calculate.py \
  tests/integration/test_shipping_e2e.py \
  tests/test_admin_console_contracts.py::test_shipping_zone_out_schema \
  tests/test_admin_console_contracts.py::test_shipping_rate_out_schema \
  -v 2>&1 | tail -10
docker compose exec api rm -rf /app/tests
```
Expected ballpark: ~24 tests passing.

- [ ] **Step 4: Commit**

```bash
git add services/api/tests/integration/test_shipping_e2e.py
git commit -m "test(shipping): end-to-end smoke test for shipping calculator"
```

---

## Done. Summary of what shipped

- New tables `shipping_zones` and `shipping_rates` with RLS, indexes, `shipping:manage` permission
- `app/services/shipping_service.py` — `calculate_shipping_options` with zone matching, condition filtering, free-shipping threshold, and FX conversion
- `app/routers/admin_shipping.py` — zone CRUD, rate CRUD (nested under zones), and `POST /v1/shipping/calculate`
- ~24 tests across service, admin CRUD, and E2E layers

## What this unlocks

- **Headless storefront API** (Phase 1): `POST /v1/shipping/calculate` is live; frontend can call it during checkout to present shipping options to shoppers
- **Hosted checkout** (Phase 2): the calculate endpoint powers the shipping step in the IMS-hosted checkout flow
- **`is_shippable` hook**: the calculator already calls `product_type_service.is_shippable` to filter digital products out of shipping calculations
- **Tax engine** (§5.5): now both product types and shipping are in place; tax can use `shipping_class` + `product_type` for rate determination

## Follow-up work (not in this plan)

- Tiered/per-kg rate bands (currently one base price per rate row; multiple rows = multiple options)
- State-level geographic targeting within a country
- Carrier API integration (UPS, FedEx, India Post, etc.)
- Dimensional weight for oversized products

---

*End of plan.*
