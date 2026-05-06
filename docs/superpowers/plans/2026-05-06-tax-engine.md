# Tax Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a configurable regional tax engine so headless storefronts and hosted checkout can compute line-item tax — with support for India's GST (CGST+SGST/IGST split), generic flat-rate regions, tax-inclusive vs tax-exclusive pricing per channel, and per-product tax class overrides.

**Architecture:** Two new tables — `tax_regions` (country/state geographic areas) and `tax_rules` (per-region, per-tax-class rates with multi-component support for GST-style split taxes). Two new columns: `tax_class` on Products (default "standard") and `tax_included_in_price` on Channels (nullable bool, default false meaning exclusive). A pure-function `tax_service.py` computes line-item tax given a cart, destination, and channel. A public `POST /v1/tax/calculate` endpoint and admin CRUD for regions/rules live in `admin_tax.py`. The existing `ShopProductTax` table (used for POS per-shop overrides) is left unchanged.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, PostgreSQL (with RLS), pytest

**Tax components model (India example):**
`tax_rules.components` is a JSONB list of `{label: str, rate_bps: int}`. Examples:
- India 18% GST intra-state: `[{"label": "CGST", "rate_bps": 900}, {"label": "SGST", "rate_bps": 900}]` (total 18%)
- India 18% GST inter-state: `[{"label": "IGST", "rate_bps": 1800}]` (total 18%)
- Generic 10% flat: `[{"label": "VAT", "rate_bps": 1000}]`
- Tax-exempt: `[]` (empty = 0% effective rate)

**Out of scope (deferred):**
- Compound/cascading taxes (tax on tax) — components are all additive.
- Province-level multi-tax (Canadian HST/GST+PST/QST) — Indonesia and Canada are deferred to post-Phase 3.
- Tax-period reporting / GSTR export — Domain 23 sub-project.
- Automatic product HSN-code → GST rate mapping — manual configuration for now.

---

### Task 1: Migration + TaxRegion + TaxRule models + new columns + contract test

**Files:**
- Create: `services/api/alembic/versions/20260512000001_tax_engine.py`
- Modify: `services/api/app/models/tables.py`
- Modify: `services/api/app/models/__init__.py`
- Modify: `services/api/tests/test_admin_console_contracts.py`

- [ ] **Step 1: Write the failing contract test**

Add to `services/api/tests/test_admin_console_contracts.py`:

```python
def test_tax_region_out_schema() -> None:
    from app.routers.admin_tax import TaxRegionOut

    r = TaxRegionOut(
        id=uuid4(),
        tenant_id=uuid4(),
        name="India GST",
        country_code="IN",
        state_code=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    d = r.model_dump(mode="json")
    assert d["country_code"] == "IN"
    assert d["state_code"] is None


def test_tax_rule_out_schema() -> None:
    from app.routers.admin_tax import TaxRuleOut

    r = TaxRuleOut(
        id=uuid4(),
        tenant_id=uuid4(),
        region_id=uuid4(),
        tax_class="standard",
        label="GST 18%",
        components=[{"label": "CGST", "rate_bps": 900}, {"label": "SGST", "rate_bps": 900}],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    d = r.model_dump(mode="json")
    assert d["tax_class"] == "standard"
    assert len(d["components"]) == 2
    assert d["components"][0]["rate_bps"] == 900
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/test_admin_console_contracts.py $CONTAINER:/app/tests/test_admin_console_contracts.py
docker compose exec api python -m pytest tests/test_admin_console_contracts.py::test_tax_region_out_schema tests/test_admin_console_contracts.py::test_tax_rule_out_schema -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routers.admin_tax'`. Stays red until Task 3.

- [ ] **Step 3: Add columns to existing tables**

In `services/api/app/models/tables.py`:

1. In the `Product` class, add after `og_image_url`:
```python
    tax_class: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # tax_class: 'standard' | 'reduced' | 'zero_rated' | 'exempt'
    # null = 'standard' (resolved at calculation time)
```

2. In the `Channel` class, add after `shop_id`:
```python
    tax_included_in_price: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    # null = False (exclusive pricing — tax added at checkout)
```

- [ ] **Step 4: Add new SQLAlchemy models**

In `services/api/app/models/tables.py`, append after `ShippingRate`:

```python
class TaxRegion(Base):
    """A geographic area with its own tax rules (country or country+state)."""
    __tablename__ = "tax_regions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "country_code", "state_code",
                         name="uq_tax_region_tenant_country_state"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    state_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TaxRule(Base):
    """Tax rate for a specific product class within a region.

    components: list of {"label": str, "rate_bps": int}
    e.g. CGST+SGST split: [{"label": "CGST", "rate_bps": 900}, {"label": "SGST", "rate_bps": 900}]
    e.g. exempt: []
    """
    __tablename__ = "tax_rules"
    __table_args__ = (
        UniqueConstraint("region_id", "tax_class", name="uq_tax_rule_region_class"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    region_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tax_regions.id", ondelete="CASCADE"), nullable=False
    )
    tax_class: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    components: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 5: Export the new models**

In `services/api/app/models/__init__.py`, add `TaxRegion` and `TaxRule` to BOTH the import block and `__all__` (alphabetical — between `StockReservation`/`StockAdjustment` and `Tenant`/`Transaction`).

- [ ] **Step 6: Write the migration**

Create `services/api/alembic/versions/20260512000001_tax_engine.py`:

```python
"""Tax engine: tax_regions + tax_rules tables, tax_class on products, tax_included_in_price on channels

Revision ID: 20260512000001
Revises: 20260511000001
Create Date: 2026-05-12 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

revision = "20260512000001"
down_revision = "20260511000001"
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
    # 1. New columns on existing tables
    op.add_column("products", sa.Column("tax_class", sa.String(32), nullable=True))
    op.add_column("channels", sa.Column("tax_included_in_price", sa.Boolean, nullable=True))

    # 2. tax_regions
    op.create_table(
        "tax_regions",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("state_code", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "country_code", "state_code",
                            name="uq_tax_region_tenant_country_state"),
    )
    op.create_index("ix_tax_regions_tenant_id", "tax_regions", ["tenant_id"])
    op.create_index("ix_tax_regions_country", "tax_regions", ["country_code"])

    # 3. tax_rules
    op.create_table(
        "tax_rules",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("region_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tax_regions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tax_class", sa.String(32), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("components", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("region_id", "tax_class", name="uq_tax_rule_region_class"),
    )
    op.create_index("ix_tax_rules_region_id", "tax_rules", ["region_id"])
    op.create_index("ix_tax_rules_tenant_id", "tax_rules", ["tenant_id"])

    # 4. Permission
    op.execute("""
        INSERT INTO permissions (id, codename, display_name, category, description)
        VALUES (gen_random_uuid(), 'tax:manage', 'Manage Tax', 'billing',
                'Manage tax regions and rules')
        ON CONFLICT (codename) DO UPDATE SET description = EXCLUDED.description
    """)
    op.execute("""
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r, permissions p
        WHERE r.name = 'owner' AND r.is_system = true
          AND p.codename = 'tax:manage'
        ON CONFLICT DO NOTHING
    """)

    # 5. RLS on new tables
    for table in ["tax_regions", "tax_rules"]:
        op.execute(f"""
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
            CREATE POLICY ims_tenant_isolation ON {table}
            USING ({_RLS_POLICY})
            WITH CHECK ({_RLS_POLICY});
        """)


def downgrade() -> None:
    for table in ["tax_rules", "tax_regions"]:
        op.execute(f"DROP POLICY IF EXISTS ims_tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.execute("""
        DELETE FROM role_permissions WHERE permission_id IN (
            SELECT id FROM permissions WHERE codename = 'tax:manage'
        )
    """)
    op.execute("DELETE FROM permissions WHERE codename = 'tax:manage'")

    op.drop_index("ix_tax_rules_tenant_id", table_name="tax_rules")
    op.drop_index("ix_tax_rules_region_id", table_name="tax_rules")
    op.drop_table("tax_rules")
    op.drop_index("ix_tax_regions_country", table_name="tax_regions")
    op.drop_index("ix_tax_regions_tenant_id", table_name="tax_regions")
    op.drop_table("tax_regions")

    op.drop_column("channels", "tax_included_in_price")
    op.drop_column("products", "tax_class")
```

- [ ] **Step 7: Run migration**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/alembic/versions/20260512000001_tax_engine.py $CONTAINER:/app/alembic/versions/
docker compose exec api alembic upgrade head
```
Expected: `Running upgrade 20260511000001 -> 20260512000001`

- [ ] **Step 8: Verify**

```bash
docker compose exec postgres psql -U ims -d ims -c "\d tax_regions"
docker compose exec postgres psql -U ims -d ims -c "\d tax_rules"
docker compose exec postgres psql -U ims -d ims -c "\d products" | grep tax_class
docker compose exec postgres psql -U ims -d ims -c "\d channels" | grep tax_included
docker compose exec postgres psql -U ims -d ims -c "SELECT codename FROM permissions WHERE codename='tax:manage'"
```
Expected: both tables described, columns visible, permission row.

- [ ] **Step 9: Commit**

```bash
git add services/api/alembic/versions/20260512000001_tax_engine.py \
        services/api/app/models/tables.py \
        services/api/app/models/__init__.py \
        services/api/tests/test_admin_console_contracts.py
git commit -m "feat(tax): add tax_regions + tax_rules tables, tax_class on products, tax_included_in_price on channels"
```

---

### Task 2: Tax calculator service

**Files:**
- Create: `services/api/app/services/tax_service.py`
- Create: `services/api/tests/services/test_tax_service.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/services/test_tax_service.py`:

```python
import uuid

import pytest

from app.models import Channel, InventoryPool, InventoryPoolShop, Product, TaxRegion, TaxRule, Shop, Tenant


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
        tax_included_in_price=False,
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def product_standard(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id, name="Widget", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=11800, product_type="physical",
    )  # tax_class=None → resolved as 'standard'
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def product_exempt(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id, name="Book", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=10000, product_type="physical", tax_class="exempt",
    )
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def india_region(db, tenant: Tenant) -> TaxRegion:
    r = TaxRegion(
        tenant_id=tenant.id, name="India GST", country_code="IN",
    )
    db.add(r)
    db.flush()
    return r


def _add_rule(db, region, tax_class, label, components):
    rule = TaxRule(
        tenant_id=region.tenant_id, region_id=region.id,
        tax_class=tax_class, label=label, components=components,
    )
    db.add(rule)
    db.flush()
    return rule


def test_exclusive_tax_added_to_price(db, tenant: Tenant, channel: Channel, product_standard: Product, india_region: TaxRegion) -> None:
    """Tax-exclusive: tax is computed on top of the line price."""
    _add_rule(db, india_region, "standard", "GST 18%",
              [{"label": "CGST", "rate_bps": 900}, {"label": "SGST", "rate_bps": 900}])

    from app.services.tax_service import calculate_tax_for_cart
    result = calculate_tax_for_cart(
        db, channel_id=channel.id, destination_country="IN",
        cart_lines=[{"product_id": product_standard.id, "quantity": 1, "unit_price_cents": 11800}],
        currency="INR",
    )
    assert result["total_tax_cents"] > 0
    line = result["lines"][0]
    assert line["tax_cents"] == 2124  # 11800 * 0.18 = 2124
    assert len(line["components"]) == 2
    assert line["components"][0]["label"] == "CGST"
    assert line["components"][0]["tax_cents"] == 1062  # 11800 * 0.09


def test_inclusive_tax_extracted_from_price(db, tenant: Tenant, shop: Shop, product_standard: Product, india_region: TaxRegion) -> None:
    """Tax-inclusive: tax is backed out of the price (price already includes tax)."""
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    incl_channel = Channel(
        tenant_id=tenant.id, type="headless", name=f"incl-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="INR",
        tax_included_in_price=True,
    )
    db.add(incl_channel)
    db.flush()

    _add_rule(db, india_region, "standard", "GST 18%",
              [{"label": "IGST", "rate_bps": 1800}])

    from app.services.tax_service import calculate_tax_for_cart
    result = calculate_tax_for_cart(
        db, channel_id=incl_channel.id, destination_country="IN",
        cart_lines=[{"product_id": product_standard.id, "quantity": 1, "unit_price_cents": 11800}],
        currency="INR",
    )
    line = result["lines"][0]
    # Inclusive: tax = price * rate / (1 + rate) = 11800 * 0.18 / 1.18 = 1800
    assert line["tax_cents"] == 1800
    assert line["price_before_tax_cents"] == 10000  # 11800 - 1800


def test_exempt_product_has_zero_tax(db, tenant: Tenant, channel: Channel, product_exempt: Product, india_region: TaxRegion) -> None:
    _add_rule(db, india_region, "standard", "GST 18%", [{"label": "GST", "rate_bps": 1800}])
    _add_rule(db, india_region, "exempt", "GST exempt", [])  # empty components = 0%

    from app.services.tax_service import calculate_tax_for_cart
    result = calculate_tax_for_cart(
        db, channel_id=channel.id, destination_country="IN",
        cart_lines=[{"product_id": product_exempt.id, "quantity": 1, "unit_price_cents": 10000}],
        currency="INR",
    )
    assert result["total_tax_cents"] == 0
    assert result["lines"][0]["tax_cents"] == 0


def test_no_region_returns_zero_tax(db, tenant: Tenant, channel: Channel, product_standard: Product) -> None:
    """When no tax region matches the destination, return 0 tax for all lines."""
    from app.services.tax_service import calculate_tax_for_cart
    result = calculate_tax_for_cart(
        db, channel_id=channel.id, destination_country="DE",
        cart_lines=[{"product_id": product_standard.id, "quantity": 1, "unit_price_cents": 10000}],
        currency="INR",
    )
    assert result["total_tax_cents"] == 0


def test_donation_product_is_exempt_by_default(db, tenant: Tenant, channel: Channel, india_region: TaxRegion) -> None:
    """Donation products use is_tax_exempt_by_default → tax is always 0 regardless of region."""
    donation = Product(
        tenant_id=tenant.id, name="Donation", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=500, product_type="donation",
    )
    db.add(donation)
    db.flush()

    _add_rule(db, india_region, "standard", "GST 18%", [{"label": "GST", "rate_bps": 1800}])

    from app.services.tax_service import calculate_tax_for_cart
    result = calculate_tax_for_cart(
        db, channel_id=channel.id, destination_country="IN",
        cart_lines=[{"product_id": donation.id, "quantity": 1, "unit_price_cents": 500}],
        currency="INR",
    )
    assert result["total_tax_cents"] == 0


def test_quantity_multiplied_correctly(db, tenant: Tenant, channel: Channel, product_standard: Product, india_region: TaxRegion) -> None:
    _add_rule(db, india_region, "standard", "GST 5%", [{"label": "GST", "rate_bps": 500}])

    from app.services.tax_service import calculate_tax_for_cart
    result = calculate_tax_for_cart(
        db, channel_id=channel.id, destination_country="IN",
        cart_lines=[{"product_id": product_standard.id, "quantity": 3, "unit_price_cents": 10000}],
        currency="INR",
    )
    # 10000 * 5% = 500 per unit; 3 units = 1500
    assert result["total_tax_cents"] == 1500
    assert result["lines"][0]["tax_cents"] == 1500


def test_state_specific_rule_preferred_over_country_rule(db, tenant: Tenant, channel: Channel, product_standard: Product) -> None:
    """State-specific region takes precedence over country-level region."""
    country_region = TaxRegion(
        tenant_id=tenant.id, name="India Generic", country_code="IN",
    )
    state_region = TaxRegion(
        tenant_id=tenant.id, name="Maharashtra", country_code="IN", state_code="MH",
    )
    db.add(country_region)
    db.add(state_region)
    db.flush()

    _add_rule(db, country_region, "standard", "GST 18%", [{"label": "GST", "rate_bps": 1800}])
    _add_rule(db, state_region, "standard", "GST 12%", [{"label": "GST", "rate_bps": 1200}])

    from app.services.tax_service import calculate_tax_for_cart
    result = calculate_tax_for_cart(
        db, channel_id=channel.id, destination_country="IN",
        destination_state="MH",
        cart_lines=[{"product_id": product_standard.id, "quantity": 1, "unit_price_cents": 10000}],
        currency="INR",
    )
    # State rule wins: 10000 * 12% = 1200
    assert result["total_tax_cents"] == 1200
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api python -m pytest tests/services/test_tax_service.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the tax service**

Create `services/api/app/services/tax_service.py`:

```python
"""Tax calculator service.

``calculate_tax_for_cart`` computes line-item tax given a cart, destination,
and channel. Returns a breakdown per line (total tax + per-component detail).

Tax inclusivity:
  channel.tax_included_in_price = False (default) → exclusive: tax added on top
    effective_tax = line_price * rate
  channel.tax_included_in_price = True → inclusive: tax backed out of price
    effective_tax = line_price * rate / (1 + rate)
    price_before_tax = line_price - effective_tax

Resolution:
  1. Find TaxRegion matching destination. State-specific takes priority over
     country-only. If no region matches, all lines get 0 tax.
  2. For each line, determine the product's effective tax class:
     - Donation product type → always exempt (0 tax)
     - Else: product.tax_class (default 'standard')
  3. Look up TaxRule for (region, tax_class). If no rule, use 0 rate.
  4. Compute tax per component, round half-up per component then sum.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.money import round_half_up_cents
from app.models import Channel, Product, TaxRegion, TaxRule
from app.services.product_type_service import is_tax_exempt_by_default


def calculate_tax_for_cart(
    db: Session,
    *,
    channel_id: UUID,
    destination_country: str,
    cart_lines: list[dict[str, Any]],
    currency: str,
    destination_state: str | None = None,
) -> dict[str, Any]:
    """Compute tax for a cart.

    Returns:
        {
            "total_tax_cents": int,
            "tax_included": bool,
            "lines": [
                {
                    "product_id": UUID,
                    "quantity": int,
                    "unit_price_cents": int,
                    "price_before_tax_cents": int,   # = unit_price when exclusive
                    "tax_cents": int,
                    "components": [{"label": str, "tax_cents": int}],
                }
            ]
        }
    """
    channel = db.get(Channel, channel_id)
    if channel is None:
        return _zero_result(cart_lines)

    tax_included = bool(channel.tax_included_in_price)
    country = destination_country.upper()
    state = destination_state.upper() if destination_state else None

    region = _find_region(db, channel.tenant_id, country, state)
    line_results = []

    for line in cart_lines:
        product = db.get(Product, line["product_id"])
        qty = line["quantity"]
        unit_price = line["unit_price_cents"]

        if product is None:
            line_results.append(_zero_line(line))
            continue

        # Donation → always tax-exempt regardless of region/class
        if is_tax_exempt_by_default(product.product_type):
            line_results.append(_zero_line(line))
            continue

        tax_class = product.tax_class or "standard"
        rule = _find_rule(db, region, tax_class) if region else None
        components = rule.components if rule else []

        line_tax, component_breakdown = _compute_tax(unit_price, qty, components, tax_included)
        price_before_tax = unit_price if not tax_included else (unit_price - line_tax // qty)

        line_results.append({
            "product_id": product.id,
            "quantity": qty,
            "unit_price_cents": unit_price,
            "price_before_tax_cents": price_before_tax if not tax_included else round_half_up_cents(unit_price * qty / (1 + _total_rate(components) / 10000)) // qty if components else unit_price,
            "tax_cents": line_tax,
            "components": component_breakdown,
        })

    total_tax = sum(ln["tax_cents"] for ln in line_results)
    return {
        "total_tax_cents": total_tax,
        "tax_included": tax_included,
        "lines": line_results,
    }


def _find_region(db: Session, tenant_id: UUID, country: str, state: str | None) -> TaxRegion | None:
    """Find the most-specific matching region (state > country)."""
    regions = db.execute(
        select(TaxRegion).where(
            TaxRegion.tenant_id == tenant_id,
            TaxRegion.country_code == country,
        )
    ).scalars().all()

    if state:
        state_match = next((r for r in regions if r.state_code and r.state_code.upper() == state), None)
        if state_match:
            return state_match

    return next((r for r in regions if r.state_code is None), None)


def _find_rule(db: Session, region: TaxRegion, tax_class: str) -> TaxRule | None:
    return db.execute(
        select(TaxRule).where(
            TaxRule.region_id == region.id,
            TaxRule.tax_class == tax_class,
        )
    ).scalar_one_or_none()


def _total_rate(components: list[dict]) -> int:
    """Sum of all component rate_bps."""
    return sum(c["rate_bps"] for c in components)


def _compute_tax(
    unit_price: int, quantity: int, components: list[dict], tax_included: bool,
) -> tuple[int, list[dict]]:
    """Return (total_tax_cents, component_breakdown) for the whole line."""
    total_rate_bps = _total_rate(components)
    line_total = unit_price * quantity

    if total_rate_bps == 0 or not components:
        return 0, []

    if tax_included:
        # Back out: line_total already contains tax
        # total_tax = line_total * rate / (1 + rate)
        effective_tax = round_half_up_cents(line_total * total_rate_bps / (10000 + total_rate_bps))
    else:
        effective_tax = round_half_up_cents(line_total * total_rate_bps / 10000)

    breakdown = []
    allocated = 0
    for i, comp in enumerate(components):
        if i == len(components) - 1:
            comp_tax = effective_tax - allocated
        else:
            comp_tax = round_half_up_cents(effective_tax * comp["rate_bps"] / total_rate_bps)
        breakdown.append({"label": comp["label"], "tax_cents": comp_tax})
        allocated += comp_tax

    return effective_tax, breakdown


def _zero_line(line: dict) -> dict:
    return {
        "product_id": line["product_id"],
        "quantity": line["quantity"],
        "unit_price_cents": line["unit_price_cents"],
        "price_before_tax_cents": line["unit_price_cents"],
        "tax_cents": 0,
        "components": [],
    }


def _zero_result(cart_lines: list[dict]) -> dict:
    return {
        "total_tax_cents": 0,
        "tax_included": False,
        "lines": [_zero_line(ln) for ln in cart_lines],
    }
```

- [ ] **Step 4: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/services/tax_service.py $CONTAINER:/app/app/services/tax_service.py
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api python -m pytest tests/services/test_tax_service.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/services/tax_service.py \
        services/api/tests/services/test_tax_service.py
git commit -m "feat(tax): add tax calculator service with region matching, inclusivity, GST components"
```

---

### Task 3: Admin CRUD + public calculate endpoint

**Files:**
- Create: `services/api/app/routers/admin_tax.py`
- Modify: `services/api/app/main.py`
- Create: `services/api/tests/routers/test_admin_tax.py`
- Create: `services/api/tests/routers/test_tax_calculate.py`

- [ ] **Step 1: Write failing tests**

Create `services/api/tests/routers/test_admin_tax.py`:

```python
# NOTE: `from __future__ import annotations` deliberately absent.

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import TaxRegion, TaxRule, Tenant


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id, role="owner", role_id=None,
        is_legacy_token=False, permissions=frozenset({"tax:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_create_tax_region(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/tax/regions", json={
        "name": "India GST",
        "country_code": "IN",
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["country_code"] == "IN"
    assert body["name"] == "India GST"
    assert body["state_code"] is None


def test_list_regions(db, tenant: Tenant, auth_headers) -> None:
    db.add(TaxRegion(tenant_id=tenant.id, name="UK VAT", country_code="GB"))
    db.commit()

    client = TestClient(app)
    resp = client.get("/v1/admin/tax/regions", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_create_rule(db, tenant: Tenant, auth_headers) -> None:
    region = TaxRegion(tenant_id=tenant.id, name="India", country_code="IN")
    db.add(region)
    db.commit()

    client = TestClient(app)
    resp = client.post(f"/v1/admin/tax/regions/{region.id}/rules", json={
        "tax_class": "standard",
        "label": "GST 18%",
        "components": [
            {"label": "CGST", "rate_bps": 900},
            {"label": "SGST", "rate_bps": 900},
        ],
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["tax_class"] == "standard"
    assert len(body["components"]) == 2


def test_list_rules(db, tenant: Tenant, auth_headers) -> None:
    region = TaxRegion(tenant_id=tenant.id, name="India", country_code="IN")
    db.add(region)
    db.flush()
    db.add(TaxRule(
        tenant_id=tenant.id, region_id=region.id,
        tax_class="standard", label="GST 18%",
        components=[{"label": "GST", "rate_bps": 1800}],
    ))
    db.commit()

    client = TestClient(app)
    resp = client.get(f"/v1/admin/tax/regions/{region.id}/rules", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_delete_region(db, tenant: Tenant, auth_headers) -> None:
    region = TaxRegion(tenant_id=tenant.id, name="Doomed", country_code="ZZ")
    db.add(region)
    db.commit()

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/tax/regions/{region.id}", headers=auth_headers)
    assert resp.status_code == 204


def test_delete_rule(db, tenant: Tenant, auth_headers) -> None:
    region = TaxRegion(tenant_id=tenant.id, name="India", country_code="IN")
    db.add(region)
    db.flush()
    rule = TaxRule(
        tenant_id=tenant.id, region_id=region.id,
        tax_class="standard", label="GST", components=[],
    )
    db.add(rule)
    db.commit()

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/tax/regions/{region.id}/rules/{rule.id}", headers=auth_headers)
    assert resp.status_code == 204


def test_negative_rate_rejected(db, tenant: Tenant, auth_headers) -> None:
    region = TaxRegion(tenant_id=tenant.id, name="India", country_code="IN")
    db.add(region)
    db.commit()

    client = TestClient(app)
    resp = client.post(f"/v1/admin/tax/regions/{region.id}/rules", json={
        "tax_class": "standard",
        "label": "Bad",
        "components": [{"label": "GST", "rate_bps": -100}],
    }, headers=auth_headers)
    assert resp.status_code == 422
```

Create `services/api/tests/routers/test_tax_calculate.py`:

```python
# NOTE: `from __future__ import annotations` deliberately absent.

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, InventoryPool, InventoryPoolShop, Product, TaxRegion, TaxRule, Shop, Tenant


@pytest.fixture()
def setup(db, tenant: Tenant, shop: Shop):
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    channel = Channel(
        tenant_id=tenant.id, type="headless", name=f"headless-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="INR",
        tax_included_in_price=False,
    )
    db.add(channel)
    db.flush()

    product = Product(
        tenant_id=tenant.id, name="Widget", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=10000, product_type="physical",
    )
    db.add(product)
    db.flush()

    region = TaxRegion(tenant_id=tenant.id, name="India", country_code="IN")
    db.add(region)
    db.flush()

    db.add(TaxRule(
        tenant_id=tenant.id, region_id=region.id,
        tax_class="standard", label="GST 18%",
        components=[{"label": "GST", "rate_bps": 1800}],
    ))
    db.commit()

    return {"channel": channel, "product": product}


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


def test_calculate_returns_tax(db, tenant: Tenant, setup, auth) -> None:
    client = TestClient(app)
    resp = client.post("/v1/tax/calculate", json={
        "channel_id": str(setup["channel"].id),
        "destination": {"country": "IN"},
        "cart_lines": [
            {"product_id": str(setup["product"].id), "quantity": 1, "unit_price_cents": 10000}
        ],
        "currency": "INR",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_tax_cents"] == 1800  # 10000 * 18%
    assert body["tax_included"] is False
    assert len(body["lines"]) == 1
    assert body["lines"][0]["tax_cents"] == 1800


def test_calculate_no_region_returns_zero(db, tenant: Tenant, setup, auth) -> None:
    """No region matches Germany → zero tax."""
    client = TestClient(app)
    resp = client.post("/v1/tax/calculate", json={
        "channel_id": str(setup["channel"].id),
        "destination": {"country": "DE"},
        "cart_lines": [
            {"product_id": str(setup["product"].id), "quantity": 1, "unit_price_cents": 10000}
        ],
        "currency": "INR",
    })
    assert resp.status_code == 200
    assert resp.json()["total_tax_cents"] == 0
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/routers/test_admin_tax.py $CONTAINER:/app/tests/routers/test_admin_tax.py
docker cp services/api/tests/routers/test_tax_calculate.py $CONTAINER:/app/tests/routers/test_tax_calculate.py
docker compose exec api python -m pytest tests/routers/test_admin_tax.py tests/routers/test_tax_calculate.py -v
docker compose exec api rm -f /app/tests/routers/test_admin_tax.py /app/tests/routers/test_tax_calculate.py
```
Expected: FAIL — router doesn't exist.

- [ ] **Step 3: Implement the router**

Create `services/api/app/routers/admin_tax.py`:

```python
"""Admin endpoints for tax regions + rules, plus the public tax calculator.

Admin CRUD requires `tax:manage` permission. The calculate endpoint is public
(no permission gate) — consumed by headless frontends and hosted checkout.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import TaxRegion, TaxRule
from app.services.tax_service import calculate_tax_for_cart

router = APIRouter(tags=["Admin Tax"])

_VALID_TAX_CLASSES = {"standard", "reduced", "zero_rated", "exempt"}


# ── Schemas ──

class TaxComponentIn(BaseModel):
    label: str = Field(min_length=1, max_length=64)
    rate_bps: int = Field(ge=0, le=100_000)


class TaxRegionIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    country_code: str = Field(min_length=2, max_length=2)
    state_code: str | None = None


class TaxRegionOut(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    country_code: str
    state_code: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaxRuleIn(BaseModel):
    tax_class: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=255)
    components: list[TaxComponentIn]


class TaxRuleOut(BaseModel):
    id: UUID
    tenant_id: UUID
    region_id: UUID
    tax_class: str
    label: str
    components: list[dict]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaxCalculateDestination(BaseModel):
    country: str = Field(min_length=2, max_length=2)
    state: str | None = None


class TaxCalculateLineIn(BaseModel):
    product_id: UUID
    quantity: int = Field(ge=1)
    unit_price_cents: int = Field(ge=0)


class TaxCalculateIn(BaseModel):
    channel_id: UUID
    destination: TaxCalculateDestination
    cart_lines: list[TaxCalculateLineIn]
    currency: str = Field(min_length=3, max_length=3)


# ── Helpers ──

def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator not assigned to a tenant",
        )
    return ctx.tenant_id


def _get_region_or_404(db: Session, region_id: UUID, tenant_id: UUID) -> TaxRegion:
    region = db.get(TaxRegion, region_id)
    if region is None or region.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Region not found")
    return region


# ── Region routes ──

@router.get(
    "/v1/admin/tax/regions",
    response_model=list[TaxRegionOut],
    dependencies=[require_permission("tax:manage")],
)
def list_regions(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[TaxRegion]:
    tenant_id = _require_tenant(ctx)
    return list(db.execute(
        select(TaxRegion).where(TaxRegion.tenant_id == tenant_id)
        .order_by(TaxRegion.country_code, TaxRegion.name)
    ).scalars().all())


@router.post(
    "/v1/admin/tax/regions",
    response_model=TaxRegionOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("tax:manage")],
)
def create_region(
    body: TaxRegionIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> TaxRegion:
    tenant_id = _require_tenant(ctx)
    region = TaxRegion(
        tenant_id=tenant_id,
        name=body.name,
        country_code=body.country_code.upper(),
        state_code=body.state_code.upper() if body.state_code else None,
    )
    db.add(region)
    db.commit()
    db.refresh(region)
    return region


@router.delete(
    "/v1/admin/tax/regions/{region_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("tax:manage")],
)
def delete_region(
    region_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    region = _get_region_or_404(db, region_id, tenant_id)
    db.delete(region)
    db.commit()


# ── Rule routes ──

@router.get(
    "/v1/admin/tax/regions/{region_id}/rules",
    response_model=list[TaxRuleOut],
    dependencies=[require_permission("tax:manage")],
)
def list_rules(
    region_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[TaxRule]:
    tenant_id = _require_tenant(ctx)
    _get_region_or_404(db, region_id, tenant_id)
    return list(db.execute(
        select(TaxRule).where(TaxRule.region_id == region_id).order_by(TaxRule.tax_class)
    ).scalars().all())


@router.post(
    "/v1/admin/tax/regions/{region_id}/rules",
    response_model=TaxRuleOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("tax:manage")],
)
def create_rule(
    region_id: UUID,
    body: TaxRuleIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> TaxRule:
    tenant_id = _require_tenant(ctx)
    region = _get_region_or_404(db, region_id, tenant_id)

    rule = TaxRule(
        tenant_id=tenant_id,
        region_id=region.id,
        tax_class=body.tax_class,
        label=body.label,
        components=[c.model_dump() for c in body.components],
    )
    db.add(rule)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A rule for tax_class '{body.tax_class}' already exists in this region",
        )
    db.refresh(rule)
    return rule


@router.delete(
    "/v1/admin/tax/regions/{region_id}/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("tax:manage")],
)
def delete_rule(
    region_id: UUID,
    rule_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    _get_region_or_404(db, region_id, tenant_id)
    rule = db.get(TaxRule, rule_id)
    if rule is None or rule.region_id != region_id or rule.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    db.delete(rule)
    db.commit()


# ── Public calculate ──

@router.post("/v1/tax/calculate")
def calculate(
    body: TaxCalculateIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> dict[str, Any]:
    """Public tax calculator consumed by headless frontends and hosted checkout."""
    return calculate_tax_for_cart(
        db,
        channel_id=body.channel_id,
        destination_country=body.destination.country,
        destination_state=body.destination.state,
        cart_lines=[line.model_dump() for line in body.cart_lines],
        currency=body.currency,
    )
```

- [ ] **Step 4: Mount the router**

In `services/api/app/main.py`, add `admin_tax` to the imports (alphabetically between `admin_suppliers` and `admin_web`) and add `app.include_router(admin_tax.router)` to the include block.

- [ ] **Step 5: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/main.py $CONTAINER:/app/app/main.py
docker cp services/api/app/routers/admin_tax.py $CONTAINER:/app/app/routers/admin_tax.py
docker cp services/api/app/services/tax_service.py $CONTAINER:/app/app/services/tax_service.py
docker cp services/api/tests $CONTAINER:/app/tests
docker compose restart api
sleep 5
docker compose exec api python -m pytest \
  tests/routers/test_admin_tax.py \
  tests/routers/test_tax_calculate.py \
  tests/test_admin_console_contracts.py::test_tax_region_out_schema \
  tests/test_admin_console_contracts.py::test_tax_rule_out_schema \
  -v
docker compose exec api rm -rf /app/tests
```
Expected: 7 admin tests + 2 calculate tests + 2 contract tests = 11 passed.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/routers/admin_tax.py \
        services/api/app/main.py \
        services/api/tests/routers/test_admin_tax.py \
        services/api/tests/routers/test_tax_calculate.py
git commit -m "feat(tax): admin CRUD for tax regions/rules + POST /v1/tax/calculate"
```

---

### Task 4: Integration smoke test

**Files:**
- Create: `services/api/tests/integration/test_tax_e2e.py`

- [ ] **Step 1: Write integration test**

Create `services/api/tests/integration/test_tax_e2e.py`:

```python
"""End-to-end smoke test for the tax engine.

Covers:
- Create India GST region + CGST+SGST rule via admin API
- Calculate tax (exclusive) for a physical product → correct split
- Tax-inclusive channel backs tax out of price
- Donation product always gets 0 tax
- State-specific rule overrides country rule
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
        tax_included_in_price=False,
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def product(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id, name="Widget", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=10000, product_type="physical",
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
        permissions=frozenset({"tax:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield
    app.dependency_overrides.clear()


def _calc(client, channel_id, product_id, subtotal=10000, country="IN", state=None, currency="INR"):
    dest = {"country": country}
    if state:
        dest["state"] = state
    return client.post("/v1/tax/calculate", json={
        "channel_id": str(channel_id),
        "destination": dest,
        "cart_lines": [{"product_id": str(product_id), "quantity": 1, "unit_price_cents": subtotal}],
        "currency": currency,
    })


def test_india_gst_split_exclusive(db, tenant: Tenant, channel: Channel, product: Product, auth) -> None:
    """Create India region + CGST+SGST rule → correct tax split on calculate."""
    client = TestClient(app)

    region = client.post("/v1/admin/tax/regions", json={
        "name": "India GST", "country_code": "IN",
    })
    assert region.status_code == 201
    region_id = region.json()["id"]

    rule = client.post(f"/v1/admin/tax/regions/{region_id}/rules", json={
        "tax_class": "standard",
        "label": "GST 18%",
        "components": [
            {"label": "CGST", "rate_bps": 900},
            {"label": "SGST", "rate_bps": 900},
        ],
    })
    assert rule.status_code == 201

    resp = _calc(client, channel.id, product.id, subtotal=10000, country="IN")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_tax_cents"] == 1800  # 10000 * 18%
    assert body["tax_included"] is False
    components = body["lines"][0]["components"]
    assert len(components) == 2
    assert components[0]["label"] == "CGST"
    assert components[0]["tax_cents"] == 900
    assert components[1]["label"] == "SGST"
    assert components[1]["tax_cents"] == 900


def test_donation_zero_tax(db, tenant: Tenant, channel: Channel, auth) -> None:
    """Donation product always gets 0 tax even when a matching region+rule exists."""
    client = TestClient(app)

    region = client.post("/v1/admin/tax/regions", json={"name": "India", "country_code": "IN"})
    region_id = region.json()["id"]
    client.post(f"/v1/admin/tax/regions/{region_id}/rules", json={
        "tax_class": "standard", "label": "GST 18%",
        "components": [{"label": "GST", "rate_bps": 1800}],
    })

    donation = Product(
        tenant_id=tenant.id, name="Donate", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=500, product_type="donation",
    )
    db.add(donation)
    db.commit()

    resp = _calc(client, channel.id, donation.id, subtotal=500)
    assert resp.status_code == 200
    assert resp.json()["total_tax_cents"] == 0


def test_no_region_zero_tax(db, tenant: Tenant, channel: Channel, product: Product, auth) -> None:
    """No India region configured → 0 tax."""
    client = TestClient(app)
    resp = _calc(client, channel.id, product.id, country="IN")
    assert resp.status_code == 200
    assert resp.json()["total_tax_cents"] == 0
```

- [ ] **Step 2: Run integration test**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest tests/integration/test_tax_e2e.py -v
docker compose exec api rm -rf /app/tests
```
Expected: 3 passed.

- [ ] **Step 3: Run full tax suite**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest \
  tests/services/test_tax_service.py \
  tests/routers/test_admin_tax.py \
  tests/routers/test_tax_calculate.py \
  tests/integration/test_tax_e2e.py \
  tests/test_admin_console_contracts.py::test_tax_region_out_schema \
  tests/test_admin_console_contracts.py::test_tax_rule_out_schema \
  -v 2>&1 | tail -5
docker compose exec api rm -rf /app/tests
```
Expected ballpark: ~23 tests passing.

- [ ] **Step 4: Commit**

```bash
git add services/api/tests/integration/test_tax_e2e.py
git commit -m "test(tax): end-to-end smoke test for tax engine"
```

---

## Done. Summary of what shipped

- New columns: `products.tax_class` (null = "standard"), `channels.tax_included_in_price` (null = false/exclusive)
- New tables `tax_regions` and `tax_rules` with RLS, indexes, `tax:manage` permission
- `app/services/tax_service.py` — `calculate_tax_for_cart` with region matching (state > country), tax class resolution, inclusive/exclusive calculation, multi-component GST-split, donation exempt
- `app/routers/admin_tax.py` — region/rule CRUD + `POST /v1/tax/calculate`
- ~23 tests

## What this unlocks

- **Hosted checkout** (Phase 2): both `POST /v1/shipping/calculate` and `POST /v1/tax/calculate` are now live — the checkout flow can present shipping options and tax breakdowns to shoppers before payment
- **Headless storefront API**: can call both calculate endpoints during the cart → checkout transition
- **India GST**: merchants can configure CGST+SGST or IGST rules per state to match their GST filing requirements
- **Discounts module** (§5.7): tax applies on post-discount prices — the discounts plan should call the tax engine after applying discounts

## Follow-up work (not in this plan)

- Tax-period export (GSTR-1/GSTR-3B reports) — Domain 23 sub-project
- Province-level multi-tax (Canadian GST+PST) — deferred post-Phase 3
- Automatic HSN-code → GST rate mapping from product fields
- Tax `rate_override` per tenant (e.g., composition scheme) — `tax_rate_overrides` table from spec
- Patch endpoint for tax rules (currently create/delete only)

---

*End of plan.*
