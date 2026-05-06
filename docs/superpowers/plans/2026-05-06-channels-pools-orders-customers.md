# Channels + Inventory Pools + Orders + Customer Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the foundational data model that lets every order, stock movement, and customer in the IMS be attributed to a sales channel — POS today, Shopify/WooCommerce/headless tomorrow — with shared inventory pools and unified per-tenant customer matching.

**Architecture:** New tables: `channels` (one per sales surface), `inventory_pools` + `inventory_pool_shops` (configurable shop sets that channels draw from), `orders` + `order_lines` + `order_payments` (the new unified order shape designed for channel-incoming orders; POS sales keep using `transactions` for now), `customer_channels` (join table tracking which channels each customer has bought from). New columns: `source_channel_id` on `stock_movements` and `transactions`, `created_via_channel_id` on `customers`. Three service modules: `channel_service.py` (POS-channel-per-shop lookup), `inventory_pool_service.py` (default pool + available stock helpers), `customer_resolver.py` (match-by-email-then-phone-then-create + channel attribution). Two admin routers: `admin_channels.py`, `admin_inventory_pools.py`. The migration auto-creates one POS channel per existing shop, one single-shop pool per shop (so a Shop A POS can't sell Shop B stock), and one tenant-wide "All Shops" pool reserved for future online channels.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, PostgreSQL (with RLS), Redis (existing), pytest

**Out of scope (deferred):**
- Connector logic for Shopify/WooCommerce/headless channels (Phase 1 sub-projects)
- Order ingest endpoints (orders table created here, populated by future connectors)
- Migrating POS sales from `transactions` to the new `orders` table (a future tech-debt cleanup; analytics layer can union the two until then)
- `catalog_filter_id` on channels (Phase 1 — channels currently publish full catalog)

---

### Task 1: Migration + SQLAlchemy models + auto-data + contract tests

**Files:**
- Create: `services/api/alembic/versions/20260507000001_channels_pools_orders.py`
- Modify: `services/api/app/models/tables.py`
- Modify: `services/api/app/models/__init__.py`
- Modify: `services/api/tests/test_admin_console_contracts.py`

- [ ] **Step 1: Write failing contract tests for the new Pydantic schemas**

Add to `services/api/tests/test_admin_console_contracts.py`:

```python
def test_channel_out_schema() -> None:
    from app.routers.admin_channels import ChannelOut

    c = ChannelOut(
        id=uuid4(),
        tenant_id=uuid4(),
        type="pos",
        name="POS at Main Street",
        status="active",
        config={},
        inventory_pool_id=uuid4(),
        currency_code="INR",
        shop_id=uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    d = c.model_dump(mode="json")
    assert d["type"] == "pos"
    assert d["status"] == "active"
    assert d["currency_code"] == "INR"


def test_inventory_pool_out_schema() -> None:
    from app.routers.admin_inventory_pools import InventoryPoolOut

    p = InventoryPoolOut(
        id=uuid4(),
        tenant_id=uuid4(),
        name="All Shops",
        fulfillment_policy="fulfill_from_primary",
        shop_ids=[uuid4(), uuid4()],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    d = p.model_dump(mode="json")
    assert d["name"] == "All Shops"
    assert len(d["shop_ids"]) == 2
    assert d["fulfillment_policy"] == "fulfill_from_primary"
```

If the imports `from datetime import UTC, datetime` and `from uuid import uuid4` are not already at the top, add them.

- [ ] **Step 2: Run tests to confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/test_admin_console_contracts.py $CONTAINER:/app/tests/test_admin_console_contracts.py
docker compose exec api python -m pytest tests/test_admin_console_contracts.py::test_channel_out_schema tests/test_admin_console_contracts.py::test_inventory_pool_out_schema -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routers.admin_channels'`. The contract tests stay red until Tasks 6 and 7.

- [ ] **Step 3: Add SQLAlchemy models**

In `services/api/app/models/tables.py`, add at the end of the file (after `FeatureFlag`):

```python
class Channel(Base):
    """A sales surface — POS at a shop, manual order entry, or a future Shopify/Woo/headless connection."""
    __tablename__ = "channels"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_channel_tenant_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    # type: 'pos' | 'manual' | 'shopify' | 'woocommerce' | 'headless'
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", server_default="active", nullable=False)
    # status: 'active' | 'paused' | 'disconnected'
    config: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="'{}'::jsonb", nullable=False)
    inventory_pool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory_pools.id", ondelete="RESTRICT"), nullable=False
    )
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    # For POS channels, shop_id is the shop the POS sells from. For other types, NULL.
    shop_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shops.id", ondelete="CASCADE"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InventoryPool(Base):
    """A configurable set of shops whose stock is sellable to channels that point at this pool."""
    __tablename__ = "inventory_pools"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_pool_tenant_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    fulfillment_policy: Mapped[str] = mapped_column(
        String(32), default="fulfill_from_primary", server_default="fulfill_from_primary", nullable=False
    )
    # fulfillment_policy: 'fulfill_from_primary' | 'split_proportionally' | 'manual_at_fulfillment'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InventoryPoolShop(Base):
    """Many-to-many: pool ↔ shop."""
    __tablename__ = "inventory_pool_shops"
    __table_args__ = (
        UniqueConstraint("pool_id", "shop_id", name="uq_pool_shop"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    pool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory_pools.id", ondelete="CASCADE"), nullable=False
    )
    shop_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("shops.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CustomerChannel(Base):
    """Tracks which channels a customer has bought from (cross-channel attribution)."""
    __tablename__ = "customer_channels"
    __table_args__ = (
        UniqueConstraint("customer_id", "channel_id", name="uq_customer_channel"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Order(Base):
    """The unified order shape designed for channel-incoming orders.

    Notes:
    - POS sales currently still use `transactions`. Migration to `orders` is a
      future cleanup; for now the analytics layer unions both.
    - `external_id` is the channel-side order ID (e.g. Shopify order GID).
      For internally-created orders (manual, headless w/ hosted checkout), NULL.
    - `shipping_address` and `billing_address` are JSONB blobs. The shape is
      decided per channel in the connector layer; the IMS does not enforce a
      universal shape here (different channels send different fields).
    """
    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("tenant_id", "channel_id", "external_id", name="uq_order_channel_external"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="RESTRICT"), nullable=False
    )
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", server_default="pending", nullable=False)
    # status: 'pending' | 'confirmed' | 'fulfilled' | 'cancelled' | 'refunded'
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    customer_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    customer_phone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    subtotal_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    shipping_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    shipping_address: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    billing_address: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OrderLine(Base):
    __tablename__ = "order_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    sku: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OrderPayment(Base):
    __tablename__ = "order_payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    provider_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    # method: 'card' | 'cash' | 'gift_card' | 'upi' | 'cod' | 'wallet' | 'other'
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="paid", server_default="paid", nullable=False)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

Then, in the existing `Transaction` class, add a new column (after `customer_phone`):

```python
    source_channel_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="SET NULL"), nullable=True
    )
```

In the existing `StockMovement` class, add (after `idempotency_key`):

```python
    source_channel_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="SET NULL"), nullable=True
    )
```

In the existing `Customer` class, add (after `notes`):

```python
    created_via_channel_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="SET NULL"), nullable=True
    )
```

- [ ] **Step 4: Export the new models**

In `services/api/app/models/__init__.py`, add to the import list and `__all__` (alphabetically):

```python
# in import block (alphabetical):
    Channel,
    CustomerChannel,
    InventoryPool,
    InventoryPoolShop,
    Order,
    OrderLine,
    OrderPayment,
```

And the same names in `__all__`.

- [ ] **Step 5: Write the Alembic migration**

Create `services/api/alembic/versions/20260507000001_channels_pools_orders.py`:

```python
"""Channels + inventory pools + orders + customer-channel attribution

Revision ID: 20260507000001
Revises: 20260506000001
Create Date: 2026-05-07 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

revision = "20260507000001"
down_revision = "20260506000001"
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
    # 1. inventory_pools (must come first — channels FK to it)
    op.create_table(
        "inventory_pools",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("fulfillment_policy", sa.String(32), nullable=False, server_default="fulfill_from_primary"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name", name="uq_pool_tenant_name"),
    )
    op.create_index("ix_inventory_pools_tenant_id", "inventory_pools", ["tenant_id"])

    # 2. inventory_pool_shops (join)
    op.create_table(
        "inventory_pool_shops",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("pool_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("inventory_pools.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shop_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("pool_id", "shop_id", name="uq_pool_shop"),
    )
    op.create_index("ix_inventory_pool_shops_pool_id", "inventory_pool_shops", ["pool_id"])
    op.create_index("ix_inventory_pool_shops_shop_id", "inventory_pool_shops", ["shop_id"])

    # 3. channels
    op.create_table(
        "channels",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("config", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("inventory_pool_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("inventory_pools.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("shop_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name", name="uq_channel_tenant_name"),
    )
    op.create_index("ix_channels_tenant_id", "channels", ["tenant_id"])
    op.create_index("ix_channels_shop_id", "channels", ["shop_id"])
    op.create_index("ix_channels_type", "channels", ["type"])

    # 4. customer_channels
    op.create_table(
        "customer_channels",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("customer_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("customer_id", "channel_id", name="uq_customer_channel"),
    )
    op.create_index("ix_customer_channels_customer_id", "customer_channels", ["customer_id"])

    # 5. orders
    op.create_table(
        "orders",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("channels.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("customer_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("customer_email", sa.String(255), nullable=True),
        sa.Column("customer_phone", sa.String(64), nullable=True),
        sa.Column("subtotal_cents", sa.Integer, nullable=False),
        sa.Column("tax_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("shipping_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("discount_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_cents", sa.Integer, nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("shipping_address", JSONB, nullable=True),
        sa.Column("billing_address", JSONB, nullable=True),
        sa.Column("placed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("raw_payload", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "channel_id", "external_id", name="uq_order_channel_external"),
    )
    op.create_index("ix_orders_tenant_id", "orders", ["tenant_id"])
    op.create_index("ix_orders_channel_id", "orders", ["channel_id"])
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"])
    op.create_index("ix_orders_placed_at", "orders", ["placed_at"])

    # 6. order_lines
    op.create_table(
        "order_lines",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("sku", sa.String(128), nullable=True),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("unit_price_cents", sa.Integer, nullable=False),
        sa.Column("line_total_cents", sa.Integer, nullable=False),
        sa.Column("tax_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("discount_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("raw_payload", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_order_lines_order_id", "order_lines", ["order_id"])

    # 7. order_payments
    op.create_table(
        "order_payments",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("provider_ref", sa.String(255), nullable=True),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("amount_cents", sa.Integer, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="paid"),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_payload", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_order_payments_order_id", "order_payments", ["order_id"])

    # 8. New columns on existing tables
    op.add_column("transactions", sa.Column(
        "source_channel_id", PG_UUID(as_uuid=True),
        sa.ForeignKey("channels.id", ondelete="SET NULL"), nullable=True,
    ))
    op.create_index("ix_transactions_source_channel_id", "transactions", ["source_channel_id"])

    op.add_column("stock_movements", sa.Column(
        "source_channel_id", PG_UUID(as_uuid=True),
        sa.ForeignKey("channels.id", ondelete="SET NULL"), nullable=True,
    ))
    op.create_index("ix_stock_movements_source_channel_id", "stock_movements", ["source_channel_id"])

    op.add_column("customers", sa.Column(
        "created_via_channel_id", PG_UUID(as_uuid=True),
        sa.ForeignKey("channels.id", ondelete="SET NULL"), nullable=True,
    ))

    # 9. Auto-create per-tenant default pool + per-shop pool + per-shop POS channel.
    # For each existing tenant:
    #   - one InventoryPool(name="All Shops", fulfillment_policy="fulfill_from_primary")
    #     containing all the tenant's shops (reserved for future online channels)
    # For each existing shop:
    #   - one InventoryPool(name="POS at {shop.name}", fulfillment_policy="fulfill_from_primary")
    #     containing only that shop
    #   - one Channel(type="pos", name="POS at {shop.name}", shop_id=shop.id,
    #     inventory_pool_id=<the single-shop pool>, currency_code=<tenant currency>)
    conn = op.get_bind()
    # Tenants and their currency (column is `default_currency_code` on tenants)
    tenant_rows = conn.execute(sa.text("""
        SELECT t.id AS tenant_id, COALESCE(t.default_currency_code, 'USD') AS currency_code
        FROM tenants t
    """)).all()

    for tenant_id, currency_code in tenant_rows:
        # Default "All Shops" pool
        default_pool_id = conn.execute(sa.text("""
            INSERT INTO inventory_pools (id, tenant_id, name, fulfillment_policy)
            VALUES (gen_random_uuid(), :tid, 'All Shops', 'fulfill_from_primary')
            RETURNING id
        """), {"tid": tenant_id}).scalar_one()

        # Add all tenant shops to the default pool
        conn.execute(sa.text("""
            INSERT INTO inventory_pool_shops (id, tenant_id, pool_id, shop_id)
            SELECT gen_random_uuid(), :tid, :pool_id, s.id
            FROM shops s
            WHERE s.tenant_id = :tid
        """), {"tid": tenant_id, "pool_id": default_pool_id})

        # Per-shop POS pool + channel
        shop_rows = conn.execute(sa.text("""
            SELECT id, name FROM shops WHERE tenant_id = :tid
        """), {"tid": tenant_id}).all()

        for shop_id, shop_name in shop_rows:
            pos_pool_id = conn.execute(sa.text("""
                INSERT INTO inventory_pools (id, tenant_id, name, fulfillment_policy)
                VALUES (gen_random_uuid(), :tid, :pname, 'fulfill_from_primary')
                RETURNING id
            """), {"tid": tenant_id, "pname": f"POS at {shop_name}"}).scalar_one()

            conn.execute(sa.text("""
                INSERT INTO inventory_pool_shops (id, tenant_id, pool_id, shop_id)
                VALUES (gen_random_uuid(), :tid, :pool_id, :shop_id)
            """), {"tid": tenant_id, "pool_id": pos_pool_id, "shop_id": shop_id})

            channel_id = conn.execute(sa.text("""
                INSERT INTO channels (id, tenant_id, type, name, status, config,
                                      inventory_pool_id, currency_code, shop_id)
                VALUES (gen_random_uuid(), :tid, 'pos', :cname, 'active', '{}'::jsonb,
                        :pool_id, :currency, :shop_id)
                RETURNING id
            """), {
                "tid": tenant_id,
                "cname": f"POS at {shop_name}",
                "pool_id": pos_pool_id,
                "currency": currency_code,
                "shop_id": shop_id,
            }).scalar_one()

            # Backfill existing transactions and stock_movements for this shop with the POS channel
            conn.execute(sa.text("""
                UPDATE transactions
                SET source_channel_id = :channel_id
                WHERE shop_id = :shop_id AND source_channel_id IS NULL
            """), {"channel_id": channel_id, "shop_id": shop_id})

            conn.execute(sa.text("""
                UPDATE stock_movements
                SET source_channel_id = :channel_id
                WHERE shop_id = :shop_id AND source_channel_id IS NULL
            """), {"channel_id": channel_id, "shop_id": shop_id})

    # 10. Seed permissions: channels:manage and inventory_pools:manage.
    # These are tenant-admin level (different from entitlements:manage which is staff-only).
    op.execute("""
        INSERT INTO permissions (id, codename, description)
        VALUES (gen_random_uuid(), 'channels:manage', 'Manage tenant sales channels')
        ON CONFLICT (codename) DO UPDATE SET description = EXCLUDED.description
    """)
    op.execute("""
        INSERT INTO permissions (id, codename, description)
        VALUES (gen_random_uuid(), 'inventory_pools:manage', 'Manage tenant inventory pools')
        ON CONFLICT (codename) DO UPDATE SET description = EXCLUDED.description
    """)

    # Grant both to tenant_admin role
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.codename = 'tenant_admin'
          AND p.codename IN ('channels:manage', 'inventory_pools:manage')
        ON CONFLICT DO NOTHING
    """)

    # 11. Enable RLS on the new tenant-scoped tables
    for table in [
        "inventory_pools", "inventory_pool_shops", "channels",
        "customer_channels", "orders", "order_lines", "order_payments",
    ]:
        op.execute(f"""
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
            CREATE POLICY ims_tenant_isolation ON {table}
            USING ({_RLS_POLICY})
            WITH CHECK ({_RLS_POLICY});
        """)


def downgrade() -> None:
    # Reverse RLS
    for table in [
        "order_payments", "order_lines", "orders",
        "customer_channels", "channels",
        "inventory_pool_shops", "inventory_pools",
    ]:
        op.execute(f"DROP POLICY IF EXISTS ims_tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    # Reverse permission grants
    op.execute("""
        DELETE FROM role_permissions
        WHERE permission_id IN (
            SELECT id FROM permissions WHERE codename IN ('channels:manage', 'inventory_pools:manage')
        )
    """)
    op.execute("""
        DELETE FROM permissions WHERE codename IN ('channels:manage', 'inventory_pools:manage')
    """)

    # Reverse column additions
    op.drop_column("customers", "created_via_channel_id")
    op.drop_index("ix_stock_movements_source_channel_id", table_name="stock_movements")
    op.drop_column("stock_movements", "source_channel_id")
    op.drop_index("ix_transactions_source_channel_id", table_name="transactions")
    op.drop_column("transactions", "source_channel_id")

    # Drop tables in reverse dependency order
    op.drop_index("ix_order_payments_order_id", table_name="order_payments")
    op.drop_table("order_payments")
    op.drop_index("ix_order_lines_order_id", table_name="order_lines")
    op.drop_table("order_lines")
    op.drop_index("ix_orders_placed_at", table_name="orders")
    op.drop_index("ix_orders_customer_id", table_name="orders")
    op.drop_index("ix_orders_channel_id", table_name="orders")
    op.drop_index("ix_orders_tenant_id", table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_customer_channels_customer_id", table_name="customer_channels")
    op.drop_table("customer_channels")
    op.drop_index("ix_channels_type", table_name="channels")
    op.drop_index("ix_channels_shop_id", table_name="channels")
    op.drop_index("ix_channels_tenant_id", table_name="channels")
    op.drop_table("channels")
    op.drop_index("ix_inventory_pool_shops_shop_id", table_name="inventory_pool_shops")
    op.drop_index("ix_inventory_pool_shops_pool_id", table_name="inventory_pool_shops")
    op.drop_table("inventory_pool_shops")
    op.drop_index("ix_inventory_pools_tenant_id", table_name="inventory_pools")
    op.drop_table("inventory_pools")
```

- [ ] **Step 6: Run migration in the running container**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/alembic/versions/20260507000001_channels_pools_orders.py $CONTAINER:/app/alembic/versions/
docker compose exec api alembic upgrade head
```
Expected: `Running upgrade 20260506000001 -> 20260507000001`

- [ ] **Step 7: Verify schema, auto-data, and RLS**

```bash
docker compose exec postgres psql -U postgres -d ims -c "\d channels"
docker compose exec postgres psql -U postgres -d ims -c "\d inventory_pools"
docker compose exec postgres psql -U postgres -d ims -c "\d orders"
docker compose exec postgres psql -U postgres -d ims -c "SELECT COUNT(*) FROM channels WHERE type='pos'"
docker compose exec postgres psql -U postgres -d ims -c "SELECT COUNT(*) FROM inventory_pools WHERE name='All Shops'"
docker compose exec postgres psql -U postgres -d ims -c "SELECT COUNT(*) FROM transactions WHERE source_channel_id IS NOT NULL"
docker compose exec postgres psql -U postgres -d ims -c "SELECT codename FROM permissions WHERE codename IN ('channels:manage','inventory_pools:manage')"
```
Expected:
- All three table descriptions printed.
- POS channel count equals number of shops (every shop got one).
- "All Shops" pool count equals number of tenants.
- transactions.source_channel_id populated on every existing transaction (count > 0 if any sales exist).
- Both new permissions returned.

- [ ] **Step 8: Commit**

```bash
git add services/api/alembic/versions/20260507000001_channels_pools_orders.py \
        services/api/app/models/tables.py \
        services/api/app/models/__init__.py \
        services/api/tests/test_admin_console_contracts.py
git commit -m "feat(channels): add channels, pools, orders, customer-channel attribution

Creates 7 new tables (channels, inventory_pools, inventory_pool_shops,
customer_channels, orders, order_lines, order_payments). Adds
source_channel_id to transactions+stock_movements and created_via_channel_id
to customers. Auto-creates a POS channel per shop with a single-shop pool;
backfills source_channel_id on existing rows. Seeds channels:manage and
inventory_pools:manage permissions, granted to tenant_admin. RLS enabled
on all new tenant-scoped tables. Contract tests stay red until Tasks 6/7
add the routers."
```

---

### Task 2: Channel service helpers

**Files:**
- Create: `services/api/app/services/channel_service.py`
- Create: `services/api/tests/services/test_channel_service.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/services/test_channel_service.py`:

```python
import uuid

import pytest

from app.models import Channel, InventoryPool, InventoryPoolShop, Shop, Tenant


@pytest.fixture()
def shop_with_pos_channel(db, tenant: Tenant, shop: Shop) -> tuple[Shop, Channel]:
    # The migration auto-created a POS channel for this shop. Find it.
    from sqlalchemy import select
    ch = db.execute(
        select(Channel).where(Channel.tenant_id == tenant.id, Channel.shop_id == shop.id, Channel.type == "pos")
    ).scalar_one_or_none()
    assert ch is not None, "Expected migration to auto-create a POS channel for this shop"
    return shop, ch


def test_get_pos_channel_for_shop_returns_existing(db, shop_with_pos_channel) -> None:
    from app.services.channel_service import get_pos_channel_for_shop
    shop, ch = shop_with_pos_channel
    found = get_pos_channel_for_shop(db, shop.id)
    assert found is not None
    assert found.id == ch.id
    assert found.type == "pos"
    assert found.shop_id == shop.id


def test_get_pos_channel_for_shop_returns_none_for_unknown(db, tenant: Tenant) -> None:
    from app.services.channel_service import get_pos_channel_for_shop
    assert get_pos_channel_for_shop(db, uuid.uuid4()) is None


def test_get_or_create_pos_channel_creates_when_missing(db, tenant: Tenant) -> None:
    """A new shop added after the migration won't have a POS channel until a sale happens.
    get_or_create_pos_channel handles that case by creating both the channel and a
    single-shop pool on demand."""
    from app.services.channel_service import get_or_create_pos_channel

    new_shop = Shop(tenant_id=tenant.id, name=f"new-shop-{uuid.uuid4().hex[:6]}")
    db.add(new_shop)
    db.flush()

    ch = get_or_create_pos_channel(db, new_shop)
    assert ch.type == "pos"
    assert ch.shop_id == new_shop.id
    assert ch.tenant_id == tenant.id
    # And the channel's pool is a single-shop pool with just this shop
    from sqlalchemy import select
    pool_shops = db.execute(
        select(InventoryPoolShop).where(InventoryPoolShop.pool_id == ch.inventory_pool_id)
    ).scalars().all()
    assert len(pool_shops) == 1
    assert pool_shops[0].shop_id == new_shop.id


def test_get_or_create_pos_channel_is_idempotent(db, shop_with_pos_channel) -> None:
    from app.services.channel_service import get_or_create_pos_channel
    shop, ch = shop_with_pos_channel
    again = get_or_create_pos_channel(db, shop)
    assert again.id == ch.id
```

If the `services` test directory doesn't have an `__init__.py`, create it as empty.

- [ ] **Step 2: Run tests to confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
mkdir -p services/api/tests/services && touch services/api/tests/services/__init__.py 2>/dev/null || true
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api python -m pytest tests/services/test_channel_service.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.channel_service'`

- [ ] **Step 3: Implement the channel service**

Create `services/api/app/services/channel_service.py`:

```python
"""Channel resolution helpers.

A POS-type channel exists 1:1 with a Shop. Existing shops got their POS channels
auto-created during migration; new shops created after the migration get one
created on first need (typically the first sale through that shop).
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Channel, InventoryPool, InventoryPoolShop, Shop, Tenant


def get_pos_channel_for_shop(db: Session, shop_id: UUID) -> Channel | None:
    """Return the POS channel for a given shop, or None if there isn't one yet."""
    return db.execute(
        select(Channel).where(Channel.shop_id == shop_id, Channel.type == "pos")
    ).scalar_one_or_none()


def get_or_create_pos_channel(db: Session, shop: Shop) -> Channel:
    """Return the shop's POS channel, creating it (and its single-shop pool) on demand.

    Used when a new shop is created post-migration and a sale happens before any
    explicit channel-management call has wired up the channel for it.
    """
    existing = get_pos_channel_for_shop(db, shop.id)
    if existing is not None:
        return existing

    # Resolve tenant currency for the new channel.
    # Column is `default_currency_code` on tenants (verified in tables.py).
    tenant = db.get(Tenant, shop.tenant_id)
    currency = (tenant.default_currency_code if tenant and tenant.default_currency_code else "USD")

    # Create a single-shop pool first (channel FK requires it to exist)
    pool = InventoryPool(
        tenant_id=shop.tenant_id,
        name=f"POS at {shop.name}",
        fulfillment_policy="fulfill_from_primary",
    )
    db.add(pool)
    db.flush()

    db.add(InventoryPoolShop(
        tenant_id=shop.tenant_id,
        pool_id=pool.id,
        shop_id=shop.id,
    ))
    db.flush()

    channel = Channel(
        tenant_id=shop.tenant_id,
        type="pos",
        name=f"POS at {shop.name}",
        status="active",
        config={},
        inventory_pool_id=pool.id,
        currency_code=currency,
        shop_id=shop.id,
    )
    db.add(channel)
    db.flush()
    return channel
```

(`Tenant.default_currency_code` was verified to exist before this plan was written.)

- [ ] **Step 4: Run tests to confirm pass**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/services/channel_service.py $CONTAINER:/app/app/services/channel_service.py
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api python -m pytest tests/services/test_channel_service.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/services/channel_service.py \
        services/api/tests/services/__init__.py \
        services/api/tests/services/test_channel_service.py
git commit -m "feat(channels): add channel_service with POS-channel-per-shop helpers"
```

---

### Task 3: Inventory pool service helpers

**Files:**
- Create: `services/api/app/services/inventory_pool_service.py`
- Create: `services/api/tests/services/test_inventory_pool_service.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/services/test_inventory_pool_service.py`:

```python
import uuid

import pytest

from app.models import Channel, InventoryPool, InventoryPoolShop, Product, Shop, StockMovement, Tenant


@pytest.fixture()
def stocked_product(db, tenant: Tenant, shop: Shop) -> Product:
    """Create a product and seed a stock movement so on_hand > 0."""
    p = Product(tenant_id=tenant.id, name="Widget", sku=f"sku-{uuid.uuid4().hex[:6]}")
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


def test_default_pool_for_tenant_returns_all_shops_pool(db, tenant: Tenant) -> None:
    from sqlalchemy import select
    from app.services.inventory_pool_service import default_pool_for_tenant

    pool = default_pool_for_tenant(db, tenant.id)
    assert pool is not None
    assert pool.name == "All Shops"
    assert pool.tenant_id == tenant.id


def test_pool_shops_returns_shop_ids(db, tenant: Tenant, shop: Shop) -> None:
    from app.services.inventory_pool_service import default_pool_for_tenant, pool_shops

    pool = default_pool_for_tenant(db, tenant.id)
    shop_ids = pool_shops(db, pool.id)
    assert shop.id in shop_ids


def test_available_stock_for_channel_sums_pool_shops(db, tenant: Tenant, shop: Shop, stocked_product: Product) -> None:
    """A channel pointing at a pool sees stock summed across the pool's shops."""
    from app.services.channel_service import get_pos_channel_for_shop
    from app.services.inventory_pool_service import available_stock_for_channel

    channel = get_pos_channel_for_shop(db, shop.id)
    assert channel is not None

    available = available_stock_for_channel(db, channel.id, stocked_product.id)
    assert available == 10


def test_available_stock_with_multi_shop_pool(db, tenant: Tenant) -> None:
    """A pool with two shops returns the sum of stock across both."""
    from app.services.inventory_pool_service import available_stock_for_channel

    shop_a = Shop(tenant_id=tenant.id, name=f"shop-a-{uuid.uuid4().hex[:6]}")
    shop_b = Shop(tenant_id=tenant.id, name=f"shop-b-{uuid.uuid4().hex[:6]}")
    db.add(shop_a)
    db.add(shop_b)
    db.flush()

    product = Product(tenant_id=tenant.id, name="Gadget", sku=f"sku-{uuid.uuid4().hex[:6]}")
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

    # Build a multi-shop pool + channel pointing at it
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
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api python -m pytest tests/services/test_inventory_pool_service.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.inventory_pool_service'`

- [ ] **Step 3: Implement the inventory pool service**

Create `services/api/app/services/inventory_pool_service.py`:

```python
"""Inventory pool helpers — default pool, membership lookup, available-stock calc.

`available_stock_for_channel` is the central function that channel-aware code
will consume. It SUMs `stock_movements.quantity_delta` across all shops in the
channel's pool, for the given product. (Soft reservations are NOT subtracted
yet; that hooks in when the stock-reservation engine sub-project ships.)
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Channel, InventoryPool, InventoryPoolShop, StockMovement


def default_pool_for_tenant(db: Session, tenant_id: UUID) -> InventoryPool | None:
    """Return the tenant's "All Shops" default pool."""
    return db.execute(
        select(InventoryPool).where(
            InventoryPool.tenant_id == tenant_id,
            InventoryPool.name == "All Shops",
        )
    ).scalar_one_or_none()


def pool_shops(db: Session, pool_id: UUID) -> list[UUID]:
    """Return the shop_ids that belong to a pool."""
    rows = db.execute(
        select(InventoryPoolShop.shop_id).where(InventoryPoolShop.pool_id == pool_id)
    ).scalars().all()
    return list(rows)


def available_stock_for_channel(
    db: Session,
    channel_id: UUID,
    product_id: UUID,
) -> int:
    """Return the available stock for a product on a channel.

    Sums stock_movements.quantity_delta across all shops in the channel's pool.
    Returns 0 if the channel doesn't exist or has no pool members.

    Soft reservations are NOT subtracted yet. When the stock reservation engine
    sub-project ships, this function gains a `- sum(active_reservations)` term.
    """
    channel = db.get(Channel, channel_id)
    if channel is None:
        return 0

    shop_ids = pool_shops(db, channel.inventory_pool_id)
    if not shop_ids:
        return 0

    total = db.execute(
        select(func.coalesce(func.sum(StockMovement.quantity_delta), 0))
        .where(
            StockMovement.product_id == product_id,
            StockMovement.shop_id.in_(shop_ids),
        )
    ).scalar_one()
    return int(total or 0)
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/services/inventory_pool_service.py $CONTAINER:/app/app/services/inventory_pool_service.py
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api python -m pytest tests/services/test_inventory_pool_service.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/services/inventory_pool_service.py \
        services/api/tests/services/test_inventory_pool_service.py
git commit -m "feat(channels): add inventory_pool_service with available_stock_for_channel"
```

---

### Task 4: Customer resolver service (unified email/phone matching + channel attribution)

**Files:**
- Create: `services/api/app/services/customer_resolver.py`
- Create: `services/api/tests/services/test_customer_resolver.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/services/test_customer_resolver.py`:

```python
import uuid

import pytest

from app.models import Channel, Customer, CustomerChannel, Shop, Tenant


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    from sqlalchemy import select
    ch = db.execute(
        select(Channel).where(Channel.tenant_id == tenant.id, Channel.shop_id == shop.id)
    ).scalar_one_or_none()
    assert ch is not None
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

    # email matches → returns the email match even though a different customer has the phone
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
    # And created_via_channel_id is set
    assert new.created_via_channel_id == channel.id


def test_writes_customer_channel_attribution(db, tenant: Tenant, channel: Channel) -> None:
    """Every resolve call records (or refreshes) a customer_channels row."""
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
    """Calling resolve twice for the same customer + channel doesn't create a second row."""
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
    """If neither email nor phone is provided, return None (anonymous order). No row created."""
    from app.services.customer_resolver import resolve_or_create_customer

    resolved = resolve_or_create_customer(db, tenant.id, channel.id, name="No Identifier")
    assert resolved is None


def test_email_normalization_is_case_insensitive(db, tenant: Tenant, channel: Channel) -> None:
    """The email matcher is case-insensitive — Foo@Bar.com and foo@bar.com map to the same customer."""
    from app.services.customer_resolver import resolve_or_create_customer

    cust1 = resolve_or_create_customer(db, tenant.id, channel.id, email="MIXED@case.COM")
    cust2 = resolve_or_create_customer(db, tenant.id, channel.id, email="mixed@case.com")
    assert cust1.id == cust2.id
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api python -m pytest tests/services/test_customer_resolver.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.customer_resolver'`

- [ ] **Step 3: Implement the customer resolver**

Create `services/api/app/services/customer_resolver.py`:

```python
"""Unified customer resolver: match by email > phone > create new, with channel attribution.

Used by every channel-incoming order pipeline:
- POS sales (sync_push.py — wired in Task 5)
- Future Shopify/Woo connectors (when they land in Phase 1)
- Future hosted-checkout / headless API order ingest

Match order is deterministic:
1. If email provided → search by email (case-insensitive). Match wins even if a
   different customer has the matching phone.
2. Else if phone provided → search by phone.
3. Else → no match. Returns None for anonymous orders. No customer is created.

A `customer_channels` row is upserted on every successful resolve to track
cross-channel attribution. `last_seen_at` is bumped on every call so the row
also doubles as recency tracking.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Customer, CustomerChannel


def resolve_or_create_customer(
    db: Session,
    tenant_id: UUID,
    channel_id: UUID,
    *,
    email: str | None = None,
    phone: str | None = None,
    name: str | None = None,
) -> Customer | None:
    """Resolve or create a customer for an incoming order.

    Returns None if neither email nor phone is provided (anonymous order).
    """
    email_norm = email.strip().lower() if email else None
    phone_norm = phone.strip() if phone else None

    if not email_norm and not phone_norm:
        return None

    customer: Customer | None = None

    if email_norm:
        customer = db.execute(
            select(Customer).where(
                Customer.tenant_id == tenant_id,
                func.lower(Customer.email) == email_norm,
            )
        ).scalar_one_or_none()

    if customer is None and phone_norm:
        customer = db.execute(
            select(Customer).where(
                Customer.tenant_id == tenant_id,
                Customer.phone == phone_norm,
            )
        ).scalar_one_or_none()

    if customer is None:
        # Create new. `phone` is NOT NULL on the model, so if missing we use a
        # placeholder derived from the email to satisfy the constraint while
        # still being unique — the multi-currency / customer-cleanup work later
        # can revisit nullable phone if desired.
        customer = Customer(
            tenant_id=tenant_id,
            phone=phone_norm or f"email:{email_norm}",
            email=email_norm,
            name=name,
            created_via_channel_id=channel_id,
        )
        db.add(customer)
        db.flush()

    _record_channel_attribution(db, tenant_id, customer.id, channel_id)
    return customer


def _record_channel_attribution(
    db: Session, tenant_id: UUID, customer_id: UUID, channel_id: UUID,
) -> None:
    """Upsert a customer_channels row, bumping last_seen_at."""
    existing = db.execute(
        select(CustomerChannel).where(
            CustomerChannel.customer_id == customer_id,
            CustomerChannel.channel_id == channel_id,
        )
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if existing is not None:
        existing.last_seen_at = now
    else:
        db.add(CustomerChannel(
            tenant_id=tenant_id,
            customer_id=customer_id,
            channel_id=channel_id,
            first_seen_at=now,
            last_seen_at=now,
        ))
    db.flush()
```

Note: the `Customer.phone` column is `NOT NULL` (existing constraint from CRM). When only email is provided and no match exists, we create a placeholder phone like `email:foo@bar.com` to keep the constraint happy. This is an acknowledged kludge — the customer-model cleanup work in a future sub-project can make `phone` nullable if needed.

- [ ] **Step 4: Run tests to confirm pass**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/services/customer_resolver.py $CONTAINER:/app/app/services/customer_resolver.py
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api python -m pytest tests/services/test_customer_resolver.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/services/customer_resolver.py \
        services/api/tests/services/test_customer_resolver.py
git commit -m "feat(channels): add customer_resolver with email>phone>create + channel attribution"
```

---

### Task 5: Wire resolver + channel attribution into sync_push.py (POS sales)

**Files:**
- Modify: `services/api/app/services/sync_push.py`
- Create: `services/api/tests/services/test_sync_push_channel_attribution.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/services/test_sync_push_channel_attribution.py`:

```python
import uuid

import pytest

from app.models import Channel, Customer, CustomerChannel, Product, Shop, StockMovement, Tenant, Transaction


@pytest.fixture()
def product(db, tenant: Tenant) -> Product:
    p = Product(tenant_id=tenant.id, name="Widget", sku=f"sku-{uuid.uuid4().hex[:6]}", unit_price_cents=500)
    db.add(p)
    db.flush()
    return p


def _build_event(shop_id, product_id, **overrides):
    """Build a sale_completed event payload for sync_push."""
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


def test_pos_sale_attributes_to_pos_channel(db, tenant: Tenant, shop: Shop, product: Product) -> None:
    from app.services.sync_push import apply_sale_completed
    from app.services.channel_service import get_pos_channel_for_shop

    pos_channel = get_pos_channel_for_shop(db, shop.id)
    assert pos_channel is not None

    event = _build_event(shop.id, product.id)
    apply_sale_completed(db, tenant.id, event, device_id=None)
    db.flush()

    from sqlalchemy import select
    txn = db.execute(
        select(Transaction).where(Transaction.client_mutation_id == event["client_mutation_id"])
    ).scalar_one()
    assert txn.source_channel_id == pos_channel.id

    movements = db.execute(
        select(StockMovement).where(StockMovement.transaction_id == txn.id)
    ).scalars().all()
    assert len(movements) >= 1
    for m in movements:
        assert m.source_channel_id == pos_channel.id


def test_pos_sale_with_email_creates_customer_attribution(db, tenant: Tenant, shop: Shop, product: Product) -> None:
    from app.services.sync_push import apply_sale_completed
    from app.services.channel_service import get_pos_channel_for_shop

    pos_channel = get_pos_channel_for_shop(db, shop.id)

    event = _build_event(
        shop.id, product.id,
        customer_email="walkin@example.com",
        customer_phone="5555555555",
        customer_name="Walk-in Customer",
    )
    apply_sale_completed(db, tenant.id, event, device_id=None)
    db.flush()

    from sqlalchemy import select
    cust = db.execute(
        select(Customer).where(Customer.tenant_id == tenant.id, Customer.email == "walkin@example.com")
    ).scalar_one()
    assert cust.created_via_channel_id == pos_channel.id

    attr = db.execute(
        select(CustomerChannel).where(
            CustomerChannel.customer_id == cust.id,
            CustomerChannel.channel_id == pos_channel.id,
        )
    ).scalar_one()
    assert attr is not None


def test_existing_customer_matched_by_email_during_pos_sale(db, tenant: Tenant, shop: Shop, product: Product) -> None:
    """An existing customer (e.g. previously created via online order) is matched, not duplicated."""
    from app.services.sync_push import apply_sale_completed

    existing = Customer(tenant_id=tenant.id, phone="6666666666", email="returning@example.com", name="Returning")
    db.add(existing)
    db.commit()

    event = _build_event(shop.id, product.id, customer_email="returning@example.com")
    apply_sale_completed(db, tenant.id, event, device_id=None)
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
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api python -m pytest tests/services/test_sync_push_channel_attribution.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: FAIL — the existing sync_push doesn't set `source_channel_id` on transactions/movements, doesn't accept `customer_email`, and doesn't write customer_channels.

- [ ] **Step 3: Read the existing sync_push code**

First, read `services/api/app/services/sync_push.py` end-to-end (it's around 300 lines). Locate:

- The `apply_sale_completed` function (the only one being changed)
- The customer resolution block (around lines 220-250 — handles `customer_id`, `customer_phone`, `customer_name`)
- The `Transaction` constructor call (around line 252)
- The `StockMovement` constructor calls (further down, in the loop that records inventory changes)

The changes needed are:

1. **Add `customer_email` to the inputs** read from the event
2. **Replace the existing inline customer resolution block** with a call to `resolve_or_create_customer`
3. **Look up the POS channel** for the shop
4. **Set `source_channel_id` on the Transaction**
5. **Set `source_channel_id` on each StockMovement created**

- [ ] **Step 4: Modify `apply_sale_completed`**

In `services/api/app/services/sync_push.py`:

Replace the existing customer-resolution block (the `# Customer resolution` block that handles `raw_customer_id`, `raw_customer_phone`, `raw_customer_name`) with a call to the new resolver, and look up the POS channel for the shop.

The exact diff (replace the section starting at `# Customer resolution`):

```python
    # Resolve POS channel for the shop
    from app.services.channel_service import get_pos_channel_for_shop, get_or_create_pos_channel

    pos_channel = get_pos_channel_for_shop(db, shop_id)
    if pos_channel is None:
        # Edge case: shop created post-migration with no POS channel yet.
        # Lazily create one (and a single-shop pool) on first sale.
        shop = db.get(Shop, shop_id)
        if shop is not None:
            pos_channel = get_or_create_pos_channel(db, shop)
    pos_channel_id = pos_channel.id if pos_channel else None

    # Customer resolution via unified resolver
    from app.services.customer_resolver import resolve_or_create_customer

    raw_customer_id = event.get("customer_id")
    raw_customer_phone = event.get("customer_phone")
    raw_customer_email = event.get("customer_email")
    raw_customer_name = event.get("customer_name")

    resolved_customer_id: uuid.UUID | None = None
    unresolved_phone: str | None = None

    if raw_customer_id:
        # Explicit customer_id (cashier picked from a list) — keep as-is for backwards compat
        cid = uuid.UUID(str(raw_customer_id))
        c = db.get(Customer, cid)
        if c and c.tenant_id == tenant_id:
            resolved_customer_id = cid
            # Still record channel attribution
            if pos_channel_id:
                from app.services.customer_resolver import _record_channel_attribution
                _record_channel_attribution(db, tenant_id, cid, pos_channel_id)
    elif raw_customer_email or raw_customer_phone:
        if pos_channel_id:
            cust = resolve_or_create_customer(
                db, tenant_id, pos_channel_id,
                email=raw_customer_email,
                phone=raw_customer_phone,
                name=raw_customer_name,
            )
            if cust is not None:
                resolved_customer_id = cust.id
            else:
                unresolved_phone = raw_customer_phone
        else:
            # No POS channel resolved — fall back to legacy phone-only attachment
            unresolved_phone = raw_customer_phone
```

Then update the `Transaction(...)` constructor call to add the `source_channel_id`:

```python
    txn = Transaction(
        tenant_id=tenant_id,
        shop_id=shop_id,
        device_id=device_id,
        user_id=user_id,
        total_cents=grand_total,
        tax_cents=tax_cents,
        client_mutation_id=client_mutation_id,
        customer_id=resolved_customer_id,
        customer_phone=unresolved_phone,
        source_channel_id=pos_channel_id,  # ← NEW
    )
```

And every `StockMovement(...)` constructor call in the file gets a new field:

```python
    db.add(StockMovement(
        tenant_id=tenant_id,
        shop_id=shop_id,
        product_id=pid,
        quantity_delta=-qty,
        movement_type="sale",
        transaction_id=txn.id,
        idempotency_key=f"sale-{txn.id}-{pid}",
        source_channel_id=pos_channel_id,  # ← NEW
    ))
```

**Important: import `Shop` if not already imported** at the top of the file. Search for `from app.models import` and ensure `Shop` is included.

- [ ] **Step 5: Run tests to confirm pass**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/services/sync_push.py $CONTAINER:/app/app/services/sync_push.py
docker cp services/api/app/services/channel_service.py $CONTAINER:/app/app/services/channel_service.py
docker cp services/api/app/services/customer_resolver.py $CONTAINER:/app/app/services/customer_resolver.py
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api python -m pytest tests/services/test_sync_push_channel_attribution.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: 3 passed.

- [ ] **Step 6: Run the existing sync tests as a regression check**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest tests/ -k "sync" -v 2>&1 | tail -20
docker compose exec api rm -rf /app/tests
```
Expected: all existing sync-related tests still pass. If any fail, the customer-resolution refactor broke a backwards-compat path; investigate and fix.

- [ ] **Step 7: Commit**

```bash
git add services/api/app/services/sync_push.py \
        services/api/tests/services/test_sync_push_channel_attribution.py
git commit -m "feat(channels): wire POS channel attribution + unified customer resolver into sync_push"
```

---

### Task 6: Admin CRUD: channels (with max_channels entitlement)

**Files:**
- Create: `services/api/app/routers/admin_channels.py`
- Modify: `services/api/app/main.py`
- Create: `services/api/tests/routers/test_admin_channels.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/routers/test_admin_channels.py`:

```python
# NOTE: `from __future__ import annotations` deliberately absent — see same comment
# in test_entitlements_dep.py (PEP 563 + FastAPI inline-route type hints).

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, Shop, Tenant, TenantLicenseCache


@pytest.fixture()
def licensed_tenant(db, tenant: Tenant) -> Tenant:
    """Pro plan with max_channels=5."""
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
def auth_headers(db, licensed_tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=uuid.uuid4(),
        tenant_id=licensed_tenant.id,
        role="tenant_admin",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset({"channels:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_list_channels_includes_auto_pos(db, shop: Shop, auth_headers) -> None:
    """The migration auto-created a POS channel for the test shop. List should include it."""
    client = TestClient(app)
    resp = client.get("/v1/admin/channels", headers=auth_headers)
    assert resp.status_code == 200
    types = {c["type"] for c in resp.json()}
    assert "pos" in types


def test_create_manual_channel(db, licensed_tenant: Tenant, auth_headers) -> None:
    from sqlalchemy import select
    from app.services.inventory_pool_service import default_pool_for_tenant

    pool = default_pool_for_tenant(db, licensed_tenant.id)

    client = TestClient(app)
    resp = client.post("/v1/admin/channels", json={
        "type": "manual",
        "name": "B2B Phone Orders",
        "inventory_pool_id": str(pool.id),
        "currency_code": "USD",
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["type"] == "manual"
    assert body["name"] == "B2B Phone Orders"
    assert body["status"] == "active"


def test_cannot_create_pos_channel_via_api(db, licensed_tenant: Tenant, auth_headers) -> None:
    """POS channels are auto-managed (one per shop). Reject explicit creation."""
    from app.services.inventory_pool_service import default_pool_for_tenant
    pool = default_pool_for_tenant(db, licensed_tenant.id)

    client = TestClient(app)
    resp = client.post("/v1/admin/channels", json={
        "type": "pos",
        "name": "rogue-pos",
        "inventory_pool_id": str(pool.id),
        "currency_code": "USD",
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert "pos" in resp.json()["detail"].lower()


def test_cannot_delete_pos_channel(db, shop: Shop, auth_headers) -> None:
    """POS channels are auto-managed. DELETE should reject."""
    from app.services.channel_service import get_pos_channel_for_shop
    pos = get_pos_channel_for_shop(db, shop.id)

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/channels/{pos.id}", headers=auth_headers)
    assert resp.status_code == 400
    assert "pos" in resp.json()["detail"].lower()


def test_max_channels_entitlement_enforced(db, tenant: Tenant) -> None:
    """A free-plan tenant (max_channels=1) hitting POST /channels with one channel
    already (the auto-created POS) gets 403 plan_upgrade_required."""
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin
    from app.services.inventory_pool_service import default_pool_for_tenant

    db.add(TenantLicenseCache(
        tenant_id=tenant.id,
        subscription_status="active",
        plan_codename="free",   # max_channels=1
        max_shops=1, max_employees=2, storage_limit_mb=500,
        last_synced_at=datetime.now(UTC),
    ))
    db.commit()

    fake_ctx = AdminContext(
        user_id=uuid.uuid4(), tenant_id=tenant.id,
        role="tenant_admin", role_id=None,
        is_legacy_token=False,
        permissions=frozenset({"channels:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    try:
        pool = default_pool_for_tenant(db, tenant.id)
        client = TestClient(app)
        resp = client.post("/v1/admin/channels", json={
            "type": "manual",
            "name": "Should-Be-Rejected",
            "inventory_pool_id": str(pool.id),
            "currency_code": "USD",
        }, headers={})
        assert resp.status_code == 403
        body = resp.json()
        assert body["detail"]["error"] == "plan_upgrade_required"
        assert body["detail"]["required_feature"] == "max_channels"
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/routers/test_admin_channels.py $CONTAINER:/app/tests/routers/test_admin_channels.py
docker compose exec api python -m pytest tests/routers/test_admin_channels.py -v
docker compose exec api rm -f /app/tests/routers/test_admin_channels.py
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routers.admin_channels'`

- [ ] **Step 3: Implement the router**

Create `services/api/app/routers/admin_channels.py`:

```python
"""Admin endpoints for managing sales channels.

POS channels are auto-managed (one per shop, created at migration time and on
shop creation). Other channel types (manual / shopify / woocommerce / headless)
can be created and deleted via this API.

Auth: requires `channels:manage` permission. Granted to `tenant_admin` by the
20260507000001 migration.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.billing.deps import EntitlementsDep
from app.db.admin_deps_db import get_db_admin
from app.models import Channel, InventoryPool

router = APIRouter(
    prefix="/v1/admin/channels",
    tags=["Admin Channels"],
    dependencies=[require_permission("channels:manage")],
)


_NON_POS_TYPES = {"manual", "shopify", "woocommerce", "headless"}


# --- Schemas ---

class ChannelIn(BaseModel):
    type: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    inventory_pool_id: UUID
    currency_code: str = Field(min_length=3, max_length=3)
    config: dict | None = None


class ChannelPatch(BaseModel):
    name: str | None = None
    status: str | None = None
    inventory_pool_id: UUID | None = None
    currency_code: str | None = None
    config: dict | None = None


class ChannelOut(BaseModel):
    id: UUID
    tenant_id: UUID
    type: str
    name: str
    status: str
    config: dict
    inventory_pool_id: UUID
    currency_code: str
    shop_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Routes ---

def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator not assigned to a tenant",
        )
    return ctx.tenant_id


@router.get("", response_model=list[ChannelOut])
def list_channels(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[Channel]:
    tenant_id = _require_tenant(ctx)
    rows = db.execute(
        select(Channel).where(Channel.tenant_id == tenant_id).order_by(Channel.type, Channel.name)
    ).scalars().all()
    return list(rows)


@router.post("", response_model=ChannelOut, status_code=status.HTTP_201_CREATED)
def create_channel(
    body: ChannelIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    ents: EntitlementsDep,
) -> Channel:
    tenant_id = _require_tenant(ctx)

    # POS channels are auto-managed
    if body.type == "pos":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="POS channels are auto-created per shop and cannot be created via API",
        )
    if body.type not in _NON_POS_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown channel type: {body.type}. Allowed: {sorted(_NON_POS_TYPES)}",
        )

    # Verify pool belongs to this tenant
    pool = db.get(InventoryPool, body.inventory_pool_id)
    if pool is None or pool.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="inventory_pool_id does not exist or does not belong to this tenant",
        )

    # Enforce max_channels entitlement
    current_count = db.execute(
        select(func.count(Channel.id)).where(Channel.tenant_id == tenant_id)
    ).scalar_one()
    limit = ents.limit("max_channels")
    if current_count >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "plan_upgrade_required",
                "required_feature": "max_channels",
                "current_plan": ents.plan_codename,
                "current_count": current_count,
                "limit": limit,
            },
        )

    row = Channel(
        tenant_id=tenant_id,
        type=body.type,
        name=body.name,
        status="active",
        config=body.config or {},
        inventory_pool_id=body.inventory_pool_id,
        currency_code=body.currency_code.upper(),
        shop_id=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{channel_id}", response_model=ChannelOut)
def update_channel(
    channel_id: UUID,
    body: ChannelPatch,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> Channel:
    tenant_id = _require_tenant(ctx)
    row = db.get(Channel, channel_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

    if row.type == "pos":
        # Allow patching name/status/config of POS channels but not their pool/currency/shop
        for forbidden in ("inventory_pool_id", "currency_code"):
            if getattr(body, forbidden) is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot change {forbidden} of a POS channel",
                )

    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        if field == "currency_code" and value is not None:
            value = value.upper()
        setattr(row, field, value)

    db.commit()
    db.refresh(row)
    return row


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_channel(
    channel_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    row = db.get(Channel, channel_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
    if row.type == "pos":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="POS channels are auto-managed and cannot be deleted via API. Delete the shop instead.",
        )
    db.delete(row)
    db.commit()
```

- [ ] **Step 4: Mount the router in main.py**

In `services/api/app/main.py`, add `admin_channels` to the imports list (alphabetically) and add `app.include_router(admin_channels.router)` to the include block.

- [ ] **Step 5: Run tests to confirm pass**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/main.py $CONTAINER:/app/app/main.py
docker cp services/api/app/routers/admin_channels.py $CONTAINER:/app/app/routers/admin_channels.py
docker cp services/api/app/services $CONTAINER:/app/app/services
docker cp services/api/tests $CONTAINER:/app/tests
docker compose restart api
sleep 5
docker compose exec api python -m pytest tests/routers/test_admin_channels.py tests/test_admin_console_contracts.py::test_channel_out_schema -v
docker compose exec api rm -rf /app/tests
```
Expected: 5 router tests + 1 contract test = 6 passed.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/routers/admin_channels.py \
        services/api/app/main.py \
        services/api/tests/routers/test_admin_channels.py
git commit -m "feat(channels): admin CRUD for channels with max_channels entitlement check"
```

---

### Task 7: Admin CRUD: inventory pools

**Files:**
- Create: `services/api/app/routers/admin_inventory_pools.py`
- Modify: `services/api/app/main.py`
- Create: `services/api/tests/routers/test_admin_inventory_pools.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/routers/test_admin_inventory_pools.py`:

```python
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import InventoryPool, InventoryPoolShop, Shop, Tenant


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        role="tenant_admin",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset({"inventory_pools:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_list_pools_includes_default(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.get("/v1/admin/inventory-pools", headers=auth_headers)
    assert resp.status_code == 200
    names = {p["name"] for p in resp.json()}
    assert "All Shops" in names


def test_create_pool_with_shops(db, tenant: Tenant, shop: Shop, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/inventory-pools", json={
        "name": "Custom Pool",
        "shop_ids": [str(shop.id)],
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Custom Pool"
    assert body["shop_ids"] == [str(shop.id)]
    assert body["fulfillment_policy"] == "fulfill_from_primary"


def test_update_pool_membership(db, tenant: Tenant, auth_headers) -> None:
    """PATCH replaces the shop set when shop_ids is provided."""
    pool = InventoryPool(tenant_id=tenant.id, name="patch-target")
    db.add(pool)
    db.flush()

    s1 = Shop(tenant_id=tenant.id, name=f"shop-1-{uuid.uuid4().hex[:6]}")
    s2 = Shop(tenant_id=tenant.id, name=f"shop-2-{uuid.uuid4().hex[:6]}")
    db.add(s1)
    db.add(s2)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=s1.id))
    db.commit()

    client = TestClient(app)
    resp = client.patch(f"/v1/admin/inventory-pools/{pool.id}", json={
        "shop_ids": [str(s2.id)],
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["shop_ids"] == [str(s2.id)]


def test_delete_pool(db, tenant: Tenant, auth_headers) -> None:
    pool = InventoryPool(tenant_id=tenant.id, name="doomed")
    db.add(pool)
    db.commit()

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/inventory-pools/{pool.id}", headers=auth_headers)
    assert resp.status_code == 204


def test_cannot_delete_pool_in_use(db, tenant: Tenant, shop: Shop, auth_headers) -> None:
    """A pool with active channels cannot be deleted (FK is RESTRICT)."""
    from app.services.channel_service import get_pos_channel_for_shop
    pos = get_pos_channel_for_shop(db, shop.id)
    pool_in_use_id = pos.inventory_pool_id

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/inventory-pools/{pool_in_use_id}", headers=auth_headers)
    assert resp.status_code == 409
    assert "in use" in resp.json()["detail"].lower()


def test_pool_shop_must_belong_to_tenant(db, tenant: Tenant, auth_headers) -> None:
    """Cross-tenant shop ID rejected."""
    other_tenant = Tenant(name=f"other-{uuid.uuid4().hex[:6]}", slug=f"other-{uuid.uuid4().hex[:8]}")
    db.add(other_tenant)
    db.flush()
    other_shop = Shop(tenant_id=other_tenant.id, name="other-shop")
    db.add(other_shop)
    db.commit()

    client = TestClient(app)
    resp = client.post("/v1/admin/inventory-pools", json={
        "name": "Cross-tenant attempt",
        "shop_ids": [str(other_shop.id)],
    }, headers=auth_headers)
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/routers/test_admin_inventory_pools.py $CONTAINER:/app/tests/routers/test_admin_inventory_pools.py
docker compose exec api python -m pytest tests/routers/test_admin_inventory_pools.py -v
docker compose exec api rm -f /app/tests/routers/test_admin_inventory_pools.py
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routers.admin_inventory_pools'`

- [ ] **Step 3: Implement the router**

Create `services/api/app/routers/admin_inventory_pools.py`:

```python
"""Admin endpoints for managing inventory pools and pool ↔ shop membership."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import InventoryPool, InventoryPoolShop, Shop

router = APIRouter(
    prefix="/v1/admin/inventory-pools",
    tags=["Admin Inventory Pools"],
    dependencies=[require_permission("inventory_pools:manage")],
)


_FULFILLMENT_POLICIES = {"fulfill_from_primary", "split_proportionally", "manual_at_fulfillment"}


# --- Schemas ---

class InventoryPoolIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    fulfillment_policy: str = "fulfill_from_primary"
    shop_ids: list[UUID] = Field(default_factory=list)


class InventoryPoolPatch(BaseModel):
    name: str | None = None
    fulfillment_policy: str | None = None
    shop_ids: list[UUID] | None = None


class InventoryPoolOut(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    fulfillment_policy: str
    shop_ids: list[UUID]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Helpers ---

def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Operator not assigned to a tenant")
    return ctx.tenant_id


def _serialize(db: Session, pool: InventoryPool) -> InventoryPoolOut:
    """Eager-load shop_ids and return the response model."""
    shop_ids = db.execute(
        select(InventoryPoolShop.shop_id).where(InventoryPoolShop.pool_id == pool.id)
    ).scalars().all()
    return InventoryPoolOut(
        id=pool.id,
        tenant_id=pool.tenant_id,
        name=pool.name,
        fulfillment_policy=pool.fulfillment_policy,
        shop_ids=list(shop_ids),
        created_at=pool.created_at,
        updated_at=pool.updated_at,
    )


def _validate_shop_ids(db: Session, tenant_id: UUID, shop_ids: list[UUID]) -> None:
    if not shop_ids:
        return
    rows = db.execute(
        select(Shop.id).where(Shop.id.in_(shop_ids), Shop.tenant_id == tenant_id)
    ).scalars().all()
    found = set(rows)
    requested = set(shop_ids)
    missing = requested - found
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"shop_ids do not belong to this tenant: {sorted(str(m) for m in missing)}",
        )


def _replace_pool_membership(
    db: Session, tenant_id: UUID, pool_id: UUID, shop_ids: list[UUID]
) -> None:
    """Delete all current memberships and re-insert from shop_ids."""
    db.execute(
        InventoryPoolShop.__table__.delete().where(InventoryPoolShop.pool_id == pool_id)
    )
    for sid in shop_ids:
        db.add(InventoryPoolShop(tenant_id=tenant_id, pool_id=pool_id, shop_id=sid))


# --- Routes ---

@router.get("", response_model=list[InventoryPoolOut])
def list_pools(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[InventoryPoolOut]:
    tenant_id = _require_tenant(ctx)
    pools = db.execute(
        select(InventoryPool).where(InventoryPool.tenant_id == tenant_id).order_by(InventoryPool.name)
    ).scalars().all()
    return [_serialize(db, p) for p in pools]


@router.post("", response_model=InventoryPoolOut, status_code=status.HTTP_201_CREATED)
def create_pool(
    body: InventoryPoolIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> InventoryPoolOut:
    tenant_id = _require_tenant(ctx)

    if body.fulfillment_policy not in _FULFILLMENT_POLICIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid fulfillment_policy. Allowed: {sorted(_FULFILLMENT_POLICIES)}",
        )

    _validate_shop_ids(db, tenant_id, body.shop_ids)

    pool = InventoryPool(
        tenant_id=tenant_id,
        name=body.name,
        fulfillment_policy=body.fulfillment_policy,
    )
    db.add(pool)
    db.flush()

    for sid in body.shop_ids:
        db.add(InventoryPoolShop(tenant_id=tenant_id, pool_id=pool.id, shop_id=sid))

    db.commit()
    db.refresh(pool)
    return _serialize(db, pool)


@router.patch("/{pool_id}", response_model=InventoryPoolOut)
def update_pool(
    pool_id: UUID,
    body: InventoryPoolPatch,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> InventoryPoolOut:
    tenant_id = _require_tenant(ctx)
    pool = db.get(InventoryPool, pool_id)
    if pool is None or pool.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Pool not found")

    if body.fulfillment_policy is not None:
        if body.fulfillment_policy not in _FULFILLMENT_POLICIES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid fulfillment_policy. Allowed: {sorted(_FULFILLMENT_POLICIES)}",
            )
        pool.fulfillment_policy = body.fulfillment_policy

    if body.name is not None:
        pool.name = body.name

    if body.shop_ids is not None:
        _validate_shop_ids(db, tenant_id, body.shop_ids)
        _replace_pool_membership(db, tenant_id, pool.id, body.shop_ids)

    db.commit()
    db.refresh(pool)
    return _serialize(db, pool)


@router.delete("/{pool_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pool(
    pool_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    pool = db.get(InventoryPool, pool_id)
    if pool is None or pool.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Pool not found")

    try:
        db.delete(pool)
        db.commit()
    except IntegrityError:
        # Channel FK is RESTRICT — a pool in use by any channel can't be deleted
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Pool is in use by one or more channels and cannot be deleted",
        )
```

- [ ] **Step 4: Mount the router in main.py**

In `services/api/app/main.py`, add `admin_inventory_pools` to the imports list (alphabetically) and `app.include_router(admin_inventory_pools.router)` to the include block.

- [ ] **Step 5: Run tests to confirm pass**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/main.py $CONTAINER:/app/app/main.py
docker cp services/api/app/routers/admin_inventory_pools.py $CONTAINER:/app/app/routers/admin_inventory_pools.py
docker cp services/api/tests $CONTAINER:/app/tests
docker compose restart api
sleep 5
docker compose exec api python -m pytest tests/routers/test_admin_inventory_pools.py tests/test_admin_console_contracts.py::test_inventory_pool_out_schema -v
docker compose exec api rm -rf /app/tests
```
Expected: 6 router tests + 1 contract test = 7 passed.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/routers/admin_inventory_pools.py \
        services/api/app/main.py \
        services/api/tests/routers/test_admin_inventory_pools.py
git commit -m "feat(channels): admin CRUD for inventory pools with shop membership"
```

---

### Task 8: Integration smoke test (end-to-end)

**Files:**
- Create: `services/api/tests/integration/test_channels_e2e.py`

This task does not add product code — only an integration test that exercises the full chain (POS sale → channel attribution → customer attribution → stock movement → admin API visibility) on representative paths.

- [ ] **Step 1: Write the integration test**

Create `services/api/tests/integration/test_channels_e2e.py`:

```python
"""End-to-end smoke test for the channels + pools + customer attribution stack.

Covers:
- POS sale with customer email → customer matched/created, channel attribution recorded,
  stock movement attributed to the POS channel
- Admin can list channels and see the auto-created POS channel
- Admin can create a manual channel and the max_channels entitlement is enforced
- Admin can create a pool with multiple shops and a channel can use it
"""
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    Channel, Customer, CustomerChannel, Product, Shop, StockMovement,
    Tenant, TenantLicenseCache, Transaction,
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
def auth(db, licensed: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=uuid.uuid4(),
        tenant_id=licensed.id,
        role="tenant_admin",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset({"channels:manage", "inventory_pools:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield
    app.dependency_overrides.clear()


def test_pos_sale_creates_full_attribution_chain(db, licensed: Tenant, shop: Shop, auth) -> None:
    """The full stack: POS sale → POS channel attribution → customer + channel record → stock movement w/ channel."""
    from sqlalchemy import select
    from app.services.channel_service import get_pos_channel_for_shop
    from app.services.sync_push import apply_sale_completed

    pos_channel = get_pos_channel_for_shop(db, shop.id)
    assert pos_channel is not None

    product = Product(tenant_id=licensed.id, name="E2E Widget", sku=f"sku-{uuid.uuid4().hex[:6]}", unit_price_cents=1000)
    db.add(product)
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
    apply_sale_completed(db, licensed.id, event, device_id=None)
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


def test_admin_lists_channels_and_creates_manual(db, licensed: Tenant, shop: Shop, auth) -> None:
    """Admin sees the auto POS channel and can add a manual channel."""
    from app.services.inventory_pool_service import default_pool_for_tenant

    client = TestClient(app)
    list_resp = client.get("/v1/admin/channels")
    assert list_resp.status_code == 200
    types_before = {c["type"] for c in list_resp.json()}
    assert "pos" in types_before

    pool = default_pool_for_tenant(db, licensed.id)
    create_resp = client.post("/v1/admin/channels", json={
        "type": "manual",
        "name": "B2B",
        "inventory_pool_id": str(pool.id),
        "currency_code": "USD",
    })
    assert create_resp.status_code == 201

    list_resp = client.get("/v1/admin/channels")
    types_after = {c["type"] for c in list_resp.json()}
    assert types_after == types_before | {"manual"}


def test_pool_lifecycle_via_admin_api(db, licensed: Tenant, shop: Shop, auth) -> None:
    """Create a pool, attach a shop, point a channel at it, verify the channel can use it."""
    client = TestClient(app)

    # Create pool with the test shop
    create_pool = client.post("/v1/admin/inventory-pools", json={
        "name": "B2B Warehouse Pool",
        "shop_ids": [str(shop.id)],
    })
    assert create_pool.status_code == 201
    pool_id = create_pool.json()["id"]

    # Create a manual channel pointing at it
    create_channel = client.post("/v1/admin/channels", json={
        "type": "manual",
        "name": "B2B Manual Channel",
        "inventory_pool_id": pool_id,
        "currency_code": "USD",
    })
    assert create_channel.status_code == 201
    channel_id = create_channel.json()["id"]

    # available_stock_for_channel works on the new channel
    from app.services.inventory_pool_service import available_stock_for_channel
    avail = available_stock_for_channel(db, uuid.UUID(channel_id), uuid.uuid4())  # unknown product → 0
    assert avail == 0
```

- [ ] **Step 2: Run the integration test**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest tests/integration/test_channels_e2e.py -v
docker compose exec api rm -rf /app/tests
```
Expected: 3 passed.

- [ ] **Step 3: Run the full channels test suite as a final sanity check**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest \
  tests/services/test_channel_service.py \
  tests/services/test_inventory_pool_service.py \
  tests/services/test_customer_resolver.py \
  tests/services/test_sync_push_channel_attribution.py \
  tests/routers/test_admin_channels.py \
  tests/routers/test_admin_inventory_pools.py \
  tests/integration/test_channels_e2e.py \
  tests/test_admin_console_contracts.py::test_channel_out_schema \
  tests/test_admin_console_contracts.py::test_inventory_pool_out_schema \
  -v
docker compose exec api rm -rf /app/tests
```
Expected ballpark: ~37 tests passing across all layers.

- [ ] **Step 4: Commit**

```bash
git add services/api/tests/integration/test_channels_e2e.py
git commit -m "test(channels): end-to-end smoke test for channels + pools + attribution"
```

---

## Done. Summary of what shipped

- 7 new tables (`channels`, `inventory_pools`, `inventory_pool_shops`, `customer_channels`, `orders`, `order_lines`, `order_payments`)
- 3 new columns (`source_channel_id` on `transactions` + `stock_movements`, `created_via_channel_id` on `customers`)
- Auto-created POS channel per existing shop with single-shop pool; auto-created "All Shops" pool per tenant
- Backfilled `source_channel_id` on existing transactions and stock movements
- 2 new permissions: `channels:manage`, `inventory_pools:manage`, both granted to `tenant_admin`
- 3 service modules: `channel_service.py`, `inventory_pool_service.py`, `customer_resolver.py`
- 2 admin routers: `admin_channels.py` (with `max_channels` entitlement check), `admin_inventory_pools.py`
- POS sales now record channel attribution + use unified customer resolver
- ~37 tests across all layers

## What this unlocks

- **Stock reservation engine** can hook into `Channel` → `InventoryPool` → shop_ids and the `available_stock_for_channel` helper
- **Customer model unification** is live — every channel-incoming order will use the same resolver
- **Webhooks-out** can attribute every event to a channel
- **Phase 1 connectors** (Shopify, Woo, headless) populate `orders` table (already exists with the right shape)
- **First entitlement integration** wired (`max_channels`) — paves the way for the other 11 entitlements to be wired into their routes

## Follow-up work (not in this plan)

- POS sales remain on `transactions` — a future cleanup can migrate to `orders` once the unified shape is proven
- The `Customer.phone` placeholder kludge (`email:foo@bar.com` when only email known) — make `phone` nullable in a future customer-cleanup sub-project
- `available_stock_for_channel` doesn't subtract reservations yet — that hooks in when the stock reservation engine sub-project ships
- `catalog_filter_id` on channels is deferred to Phase 1

---

*End of plan.*
