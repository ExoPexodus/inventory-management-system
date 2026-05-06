# Discounts Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add first-class discounts so merchants can offer coupon codes and automatic promotions — percentage off, fixed amount off, and free shipping — with usage limits, date windows, and a minimum cart total condition.

**Architecture:** Two new tables — `discounts` (the discount definition) and `discount_uses` (a ledger of every time a discount was applied, for usage-limit enforcement). A `discount_service.py` contains `apply_discount` which validates eligibility, computes the discount amount using the `Money` value type, and optionally records a tentative use on a cart_token. A public `POST /v1/discounts/apply` endpoint exposes the calculator to headless frontends and hosted checkout. Admin CRUD for discounts lives in `admin_discounts.py`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, PostgreSQL (with RLS), pytest

**Out of scope (deferred to Domain 56 — Advanced Promotions):**
- buy-X-get-Y offer type.
- Product-specific / category-specific / customer-segment conditions.
- Stacking multiple discounts on one cart (for now: one discount per cart, determined by priority when multiple are eligible).
- Promotional bundle pricing and loyalty multiplier events.

---

### Task 1: Migration + Discount + DiscountUse models + contract test

**Files:**
- Create: `services/api/alembic/versions/20260513000001_discounts.py`
- Modify: `services/api/app/models/tables.py`
- Modify: `services/api/app/models/__init__.py`
- Modify: `services/api/tests/test_admin_console_contracts.py`

- [ ] **Step 1: Write the failing contract test**

Add to `services/api/tests/test_admin_console_contracts.py`:

```python
def test_discount_out_schema() -> None:
    from app.routers.admin_discounts import DiscountOut

    d = DiscountOut(
        id=uuid4(),
        tenant_id=uuid4(),
        channel_id=None,
        name="Summer Sale",
        code="SUMMER20",
        discount_type="percentage",
        value_bps=2000,
        value_cents=None,
        status="active",
        stackable=False,
        priority=0,
        min_subtotal_cents=None,
        max_uses_total=None,
        max_uses_per_customer=None,
        starts_at=None,
        expires_at=None,
        times_used=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    dumped = d.model_dump(mode="json")
    assert dumped["code"] == "SUMMER20"
    assert dumped["discount_type"] == "percentage"
    assert dumped["value_bps"] == 2000
    assert dumped["times_used"] == 0
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/test_admin_console_contracts.py $CONTAINER:/app/tests/test_admin_console_contracts.py
docker compose exec api python -m pytest tests/test_admin_console_contracts.py::test_discount_out_schema -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routers.admin_discounts'`. Stays red until Task 3.

- [ ] **Step 3: Add SQLAlchemy models**

In `services/api/app/models/tables.py`, append after `TaxRule`:

```python
class Discount(Base):
    """A promotion definition: code-based coupon or automatic discount.

    Types:
      percentage   — reduce cart subtotal by value_bps basis points
                     (1000 bps = 10 %, 2000 = 20 %, etc.)
      fixed_amount — reduce cart subtotal by value_cents (in channel currency)
      free_shipping — zero out the shipping cost (no amount deducted from items)

    A discount without a code (code=NULL) is applied automatically when its
    conditions are met. Only one discount is applied per cart — when multiple
    qualify, the one with the highest priority wins (ties broken by largest
    discount_amount, then by created_at desc).

    channel_id=NULL means the discount applies to any channel of this tenant.
    """
    __tablename__ = "discounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    channel_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    discount_type: Mapped[str] = mapped_column(String(32), nullable=False)
    value_bps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    value_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", server_default="active", nullable=False)
    stackable: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    min_subtotal_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_uses_total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_uses_per_customer: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DiscountUse(Base):
    """Ledger entry recording each application of a discount.

    Written when a discount is *applied to a cart* (cart_token set, order_id=NULL).
    When the order completes, the row is updated with the order_id.
    When the cart is abandoned, the row is deleted by a cleanup sweep.
    This is how usage limits are enforced in real time.
    """
    __tablename__ = "discount_uses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    discount_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("discounts.id", ondelete="CASCADE"), nullable=False
    )
    cart_token: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    customer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    discount_amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 4: Export the models**

In `services/api/app/models/__init__.py`, add `Discount` and `DiscountUse` to BOTH the import block and `__all__` (alphabetical — between `Device`/`EnrollmentToken` and `FeatureFlag`).

- [ ] **Step 5: Write the migration**

Create `services/api/alembic/versions/20260513000001_discounts.py`:

```python
"""Discounts module: discounts + discount_uses tables

Revision ID: 20260513000001
Revises: 20260512000001
Create Date: 2026-05-13 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "20260513000001"
down_revision = "20260512000001"
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
    op.create_table(
        "discounts",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("code", sa.String(128), nullable=True),
        sa.Column("discount_type", sa.String(32), nullable=False),
        sa.Column("value_bps", sa.Integer, nullable=True),
        sa.Column("value_cents", sa.Integer, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("stackable", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("min_subtotal_cents", sa.Integer, nullable=True),
        sa.Column("max_uses_total", sa.Integer, nullable=True),
        sa.Column("max_uses_per_customer", sa.Integer, nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_discounts_tenant_id", "discounts", ["tenant_id"])
    op.create_index("ix_discounts_code", "discounts", ["tenant_id", "code"],
                    unique=True, postgresql_where=sa.text("code IS NOT NULL"))
    op.create_index("ix_discounts_status", "discounts", ["tenant_id", "status"])

    op.create_table(
        "discount_uses",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("discount_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("discounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cart_token", sa.String(128), nullable=True),
        sa.Column("customer_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("order_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("discount_amount_cents", sa.Integer, nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_discount_uses_discount_id", "discount_uses", ["discount_id"])
    op.create_index("ix_discount_uses_customer_id", "discount_uses", ["customer_id"])
    op.create_index("ix_discount_uses_tenant_id", "discount_uses", ["tenant_id"])

    op.execute("""
        INSERT INTO permissions (id, codename, display_name, category, description)
        VALUES (gen_random_uuid(), 'discounts:manage', 'Manage Discounts', 'billing',
                'Create, edit, and delete discount codes and promotions')
        ON CONFLICT (codename) DO UPDATE SET description = EXCLUDED.description
    """)
    op.execute("""
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r, permissions p
        WHERE r.name = 'owner' AND r.is_system = true
          AND p.codename = 'discounts:manage'
        ON CONFLICT DO NOTHING
    """)

    for table in ["discounts", "discount_uses"]:
        op.execute(f"""
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
            CREATE POLICY ims_tenant_isolation ON {table}
            USING ({_RLS_POLICY})
            WITH CHECK ({_RLS_POLICY});
        """)


def downgrade() -> None:
    for table in ["discount_uses", "discounts"]:
        op.execute(f"DROP POLICY IF EXISTS ims_tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.execute("""
        DELETE FROM role_permissions WHERE permission_id IN (
            SELECT id FROM permissions WHERE codename = 'discounts:manage'
        )
    """)
    op.execute("DELETE FROM permissions WHERE codename = 'discounts:manage'")

    op.drop_index("ix_discount_uses_tenant_id", table_name="discount_uses")
    op.drop_index("ix_discount_uses_customer_id", table_name="discount_uses")
    op.drop_index("ix_discount_uses_discount_id", table_name="discount_uses")
    op.drop_table("discount_uses")
    op.drop_index("ix_discounts_status", table_name="discounts")
    op.drop_index("ix_discounts_code", table_name="discounts")
    op.drop_index("ix_discounts_tenant_id", table_name="discounts")
    op.drop_table("discounts")
```

- [ ] **Step 6: Run migration**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/alembic/versions/20260513000001_discounts.py $CONTAINER:/app/alembic/versions/
docker compose exec api alembic upgrade head
```
Expected: `Running upgrade 20260512000001 -> 20260513000001`

- [ ] **Step 7: Verify**

```bash
docker compose exec postgres psql -U ims -d ims -c "\d discounts"
docker compose exec postgres psql -U ims -d ims -c "\d discount_uses"
docker compose exec postgres psql -U ims -d ims -c "SELECT codename FROM permissions WHERE codename='discounts:manage'"
```
Expected: both tables described, permission row.

- [ ] **Step 8: Commit**

```bash
git add services/api/alembic/versions/20260513000001_discounts.py \
        services/api/app/models/tables.py \
        services/api/app/models/__init__.py \
        services/api/tests/test_admin_console_contracts.py
git commit -m "feat(discounts): add discounts + discount_uses tables"
```

---

### Task 2: Discount application service

**Files:**
- Create: `services/api/app/services/discount_service.py`
- Create: `services/api/tests/services/test_discount_service.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/services/test_discount_service.py`:

```python
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models import Channel, Discount, DiscountUse, InventoryPool, InventoryPoolShop, Shop, Tenant


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
    disc = _discount(db, tenant,
        name="20% off", code="TWENTY", discount_type="percentage",
        value_bps=2000, status="active",
    )

    from app.services.discount_service import apply_discount
    result = apply_discount(
        db, tenant_id=tenant.id, channel_id=channel.id,
        code="TWENTY", cart_subtotal_cents=10000,
    )
    assert result["discount_amount_cents"] == 2000  # 10000 * 20% = 2000
    assert result["final_total_cents"] == 8000
    assert result["is_free_shipping"] is False
    assert result["discount_id"] == disc.id


def test_fixed_amount_discount(db, tenant: Tenant, channel: Channel) -> None:
    _discount(db, tenant,
        name="₹500 off", code="FLAT500", discount_type="fixed_amount",
        value_cents=500, status="active",
    )

    from app.services.discount_service import apply_discount
    result = apply_discount(
        db, tenant_id=tenant.id, channel_id=channel.id,
        code="FLAT500", cart_subtotal_cents=3000,
    )
    assert result["discount_amount_cents"] == 500
    assert result["final_total_cents"] == 2500


def test_fixed_amount_capped_at_cart_total(db, tenant: Tenant, channel: Channel) -> None:
    """Fixed discount that exceeds the cart total is capped at cart total (no negative totals)."""
    _discount(db, tenant,
        name="₹2000 off", code="BIG2000", discount_type="fixed_amount",
        value_cents=2000, status="active",
    )

    from app.services.discount_service import apply_discount
    result = apply_discount(
        db, tenant_id=tenant.id, channel_id=channel.id,
        code="BIG2000", cart_subtotal_cents=1500,
    )
    assert result["discount_amount_cents"] == 1500  # capped
    assert result["final_total_cents"] == 0


def test_free_shipping_discount(db, tenant: Tenant, channel: Channel) -> None:
    _discount(db, tenant,
        name="Free Ship", code="FREESHIP", discount_type="free_shipping",
        status="active",
    )

    from app.services.discount_service import apply_discount
    result = apply_discount(
        db, tenant_id=tenant.id, channel_id=channel.id,
        code="FREESHIP", cart_subtotal_cents=5000,
    )
    assert result["discount_amount_cents"] == 0
    assert result["final_total_cents"] == 5000
    assert result["is_free_shipping"] is True


def test_expired_code_rejected(db, tenant: Tenant, channel: Channel) -> None:
    from app.services.discount_service import DiscountNotEligibleError
    _discount(db, tenant,
        name="Expired", code="OLD", discount_type="percentage",
        value_bps=1000, status="active",
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )

    with pytest.raises(DiscountNotEligibleError, match="expired"):
        from app.services.discount_service import apply_discount
        apply_discount(db, tenant_id=tenant.id, channel_id=channel.id,
                      code="OLD", cart_subtotal_cents=5000)


def test_not_started_code_rejected(db, tenant: Tenant, channel: Channel) -> None:
    from app.services.discount_service import DiscountNotEligibleError
    _discount(db, tenant,
        name="Future", code="SOON", discount_type="percentage",
        value_bps=500, status="active",
        starts_at=datetime.now(UTC) + timedelta(days=5),
    )

    with pytest.raises(DiscountNotEligibleError, match="not yet"):
        from app.services.discount_service import apply_discount
        apply_discount(db, tenant_id=tenant.id, channel_id=channel.id,
                      code="SOON", cart_subtotal_cents=5000)


def test_min_subtotal_condition_enforced(db, tenant: Tenant, channel: Channel) -> None:
    from app.services.discount_service import DiscountNotEligibleError
    _discount(db, tenant,
        name="Min 1000", code="MIN1000", discount_type="percentage",
        value_bps=1000, status="active", min_subtotal_cents=10000,
    )

    with pytest.raises(DiscountNotEligibleError, match="minimum"):
        from app.services.discount_service import apply_discount
        apply_discount(db, tenant_id=tenant.id, channel_id=channel.id,
                      code="MIN1000", cart_subtotal_cents=5000)


def test_global_usage_limit_enforced(db, tenant: Tenant, channel: Channel) -> None:
    from app.services.discount_service import DiscountNotEligibleError
    disc = _discount(db, tenant,
        name="Limited", code="LTD", discount_type="percentage",
        value_bps=500, status="active", max_uses_total=2,
    )
    # Add 2 existing uses
    for _ in range(2):
        db.add(DiscountUse(
            tenant_id=tenant.id, discount_id=disc.id,
            discount_amount_cents=50,
        ))
    db.flush()

    with pytest.raises(DiscountNotEligibleError, match="usage limit"):
        from app.services.discount_service import apply_discount
        apply_discount(db, tenant_id=tenant.id, channel_id=channel.id,
                      code="LTD", cart_subtotal_cents=1000)


def test_per_customer_limit_enforced(db, tenant: Tenant, channel: Channel) -> None:
    from app.services.discount_service import DiscountNotEligibleError
    customer_id = uuid.uuid4()
    disc = _discount(db, tenant,
        name="Once per customer", code="ONCE", discount_type="percentage",
        value_bps=500, status="active", max_uses_per_customer=1,
    )
    db.add(DiscountUse(
        tenant_id=tenant.id, discount_id=disc.id,
        customer_id=customer_id, discount_amount_cents=50,
    ))
    db.flush()

    with pytest.raises(DiscountNotEligibleError, match="customer"):
        from app.services.discount_service import apply_discount
        apply_discount(db, tenant_id=tenant.id, channel_id=channel.id,
                      code="ONCE", cart_subtotal_cents=1000,
                      customer_id=customer_id)


def test_unknown_code_raises(db, tenant: Tenant, channel: Channel) -> None:
    from app.services.discount_service import DiscountNotFoundError
    with pytest.raises(DiscountNotFoundError):
        from app.services.discount_service import apply_discount
        apply_discount(db, tenant_id=tenant.id, channel_id=channel.id,
                      code="DOESNOTEXIST", cart_subtotal_cents=1000)


def test_automatic_discount_found_without_code(db, tenant: Tenant, channel: Channel) -> None:
    """An automatic discount (code=None, status=active) is returned when no code is supplied."""
    _discount(db, tenant,
        name="Always 5% off", code=None, discount_type="percentage",
        value_bps=500, status="active",
    )

    from app.services.discount_service import apply_discount
    result = apply_discount(
        db, tenant_id=tenant.id, channel_id=channel.id,
        code=None, cart_subtotal_cents=10000,
    )
    assert result["discount_amount_cents"] == 500


def test_paused_discount_not_applied(db, tenant: Tenant, channel: Channel) -> None:
    from app.services.discount_service import DiscountNotFoundError
    _discount(db, tenant,
        name="Paused", code="PAUSED", discount_type="percentage",
        value_bps=1000, status="paused",
    )
    with pytest.raises(DiscountNotFoundError):
        from app.services.discount_service import apply_discount
        apply_discount(db, tenant_id=tenant.id, channel_id=channel.id,
                      code="PAUSED", cart_subtotal_cents=5000)
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api python -m pytest tests/services/test_discount_service.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement the discount service**

Create `services/api/app/services/discount_service.py`:

```python
"""Discount application service.

``apply_discount`` validates a discount code (or finds an applicable automatic
discount) and returns the discount amount. It does NOT write a DiscountUse row
— the caller decides whether to commit a tentative use or wait until order
confirmation. Use ``record_discount_use`` for the actual ledger write.

Eligibility checks:
  1. Discount exists and is active
  2. Falls within [starts_at, expires_at] window (both nullable = no limit)
  3. Minimum cart subtotal met (if set)
  4. Global usage limit not exceeded (sum of DiscountUse rows)
  5. Per-customer limit not exceeded (if customer_id provided)

Amount calculation:
  percentage   → round_half_up_cents(subtotal * value_bps / 10000), capped at subtotal
  fixed_amount → min(value_cents, subtotal) so total never goes negative
  free_shipping → discount_amount_cents = 0, is_free_shipping = True
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.billing.money import round_half_up_cents
from app.models import Discount, DiscountUse


class DiscountNotFoundError(LookupError):
    """No matching active discount found for this code / tenant."""


class DiscountNotEligibleError(ValueError):
    """Discount found but conditions not met for this cart / customer."""


def apply_discount(
    db: Session,
    *,
    tenant_id: UUID,
    channel_id: UUID,
    cart_subtotal_cents: int,
    code: str | None = None,
    customer_id: UUID | None = None,
) -> dict[str, Any]:
    """Validate a discount and compute the amount.

    Returns:
        {
            "discount_id": UUID,
            "name": str,
            "discount_type": str,
            "discount_amount_cents": int,
            "final_total_cents": int,
            "is_free_shipping": bool,
        }

    Raises:
        DiscountNotFoundError: no active discount for this code/tenant
        DiscountNotEligibleError: discount found but conditions not satisfied
    """
    discount = _find_discount(db, tenant_id, channel_id, code)
    _check_window(discount)
    _check_min_subtotal(discount, cart_subtotal_cents)
    _check_global_limit(db, discount)
    if customer_id:
        _check_customer_limit(db, discount, customer_id)

    amount, is_free_shipping = _compute_amount(discount, cart_subtotal_cents)
    return {
        "discount_id": discount.id,
        "name": discount.name,
        "discount_type": discount.discount_type,
        "discount_amount_cents": amount,
        "final_total_cents": cart_subtotal_cents - amount,
        "is_free_shipping": is_free_shipping,
    }


def record_discount_use(
    db: Session,
    *,
    tenant_id: UUID,
    discount_id: UUID,
    discount_amount_cents: int,
    cart_token: str | None = None,
    customer_id: UUID | None = None,
    order_id: UUID | None = None,
) -> DiscountUse:
    """Write a ledger entry for a discount application. Flush but do not commit."""
    use = DiscountUse(
        tenant_id=tenant_id,
        discount_id=discount_id,
        cart_token=cart_token,
        customer_id=customer_id,
        order_id=order_id,
        discount_amount_cents=discount_amount_cents,
    )
    db.add(use)
    db.flush()
    return use


def _find_discount(db: Session, tenant_id: UUID, channel_id: UUID, code: str | None) -> Discount:
    q = select(Discount).where(
        Discount.tenant_id == tenant_id,
        Discount.status == "active",
    )
    if code is not None:
        # Case-insensitive code match
        q = q.where(func.upper(Discount.code) == code.upper())
    else:
        # Automatic discounts only (code IS NULL)
        q = q.where(Discount.code.is_(None))

    # Channel filter: channel-specific OR tenant-wide (channel_id=NULL)
    q = q.where(
        (Discount.channel_id == channel_id) | (Discount.channel_id.is_(None))
    )
    # For automatic: pick highest priority, then largest potential discount
    q = q.order_by(Discount.priority.desc(), Discount.value_bps.desc().nullslast(),
                   Discount.value_cents.desc().nullslast())

    discount = db.execute(q).scalars().first()
    if discount is None:
        raise DiscountNotFoundError(
            f"No active discount found for code={code!r} on tenant {tenant_id}"
        )
    return discount


def _check_window(discount: Discount) -> None:
    now = datetime.now(UTC)
    if discount.starts_at and discount.starts_at > now:
        raise DiscountNotEligibleError(
            f"Discount {discount.code!r} is not yet valid (starts {discount.starts_at.isoformat()})"
        )
    if discount.expires_at and discount.expires_at <= now:
        raise DiscountNotEligibleError(
            f"Discount {discount.code!r} has expired"
        )


def _check_min_subtotal(discount: Discount, cart_subtotal_cents: int) -> None:
    if discount.min_subtotal_cents and cart_subtotal_cents < discount.min_subtotal_cents:
        raise DiscountNotEligibleError(
            f"Cart minimum {discount.min_subtotal_cents} not met (cart is {cart_subtotal_cents})"
        )


def _check_global_limit(db: Session, discount: Discount) -> None:
    if discount.max_uses_total is None:
        return
    count = db.execute(
        select(func.count(DiscountUse.id)).where(DiscountUse.discount_id == discount.id)
    ).scalar_one()
    if count >= discount.max_uses_total:
        raise DiscountNotEligibleError(
            f"Discount {discount.code!r} has reached its global usage limit"
        )


def _check_customer_limit(db: Session, discount: Discount, customer_id: UUID) -> None:
    if discount.max_uses_per_customer is None:
        return
    count = db.execute(
        select(func.count(DiscountUse.id)).where(
            DiscountUse.discount_id == discount.id,
            DiscountUse.customer_id == customer_id,
        )
    ).scalar_one()
    if count >= discount.max_uses_per_customer:
        raise DiscountNotEligibleError(
            f"Discount {discount.code!r} has reached its per-customer usage limit"
        )


def _compute_amount(discount: Discount, cart_subtotal_cents: int) -> tuple[int, bool]:
    """Return (discount_amount_cents, is_free_shipping)."""
    dt = discount.discount_type
    if dt == "free_shipping":
        return 0, True
    if dt == "percentage":
        raw = round_half_up_cents(cart_subtotal_cents * (discount.value_bps or 0) / 10000)
        return min(raw, cart_subtotal_cents), False
    if dt == "fixed_amount":
        return min(discount.value_cents or 0, cart_subtotal_cents), False
    return 0, False
```

- [ ] **Step 4: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/services/discount_service.py $CONTAINER:/app/app/services/discount_service.py
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api python -m pytest tests/services/test_discount_service.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/services/discount_service.py \
        services/api/tests/services/test_discount_service.py
git commit -m "feat(discounts): add discount application service with eligibility checks"
```

---

### Task 3: Admin CRUD + public apply endpoint

**Files:**
- Create: `services/api/app/routers/admin_discounts.py`
- Modify: `services/api/app/main.py`
- Create: `services/api/tests/routers/test_admin_discounts.py`
- Create: `services/api/tests/routers/test_discount_apply.py`

- [ ] **Step 1: Write failing tests**

Create `services/api/tests/routers/test_admin_discounts.py`:

```python
# NOTE: `from __future__ import annotations` deliberately absent.

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, Discount, InventoryPool, InventoryPoolShop, Shop, Tenant


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id, role="owner", role_id=None,
        is_legacy_token=False, permissions=frozenset({"discounts:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_create_percentage_discount(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/discounts", json={
        "name": "Summer 20% Off",
        "code": "SUMMER20",
        "discount_type": "percentage",
        "value_bps": 2000,
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["code"] == "SUMMER20"
    assert body["discount_type"] == "percentage"
    assert body["value_bps"] == 2000
    assert body["status"] == "active"
    assert body["times_used"] == 0


def test_create_fixed_amount_discount(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/discounts", json={
        "name": "₹500 off",
        "code": "FLAT500",
        "discount_type": "fixed_amount",
        "value_cents": 500,
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["value_cents"] == 500


def test_create_free_shipping_discount(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/discounts", json={
        "name": "Free Shipping",
        "code": "FREESHIP",
        "discount_type": "free_shipping",
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["discount_type"] == "free_shipping"


def test_list_discounts(db, tenant: Tenant, auth_headers) -> None:
    db.add(Discount(tenant_id=tenant.id, name="D1", code="C1",
                    discount_type="percentage", value_bps=1000, status="active"))
    db.add(Discount(tenant_id=tenant.id, name="D2", code="C2",
                    discount_type="fixed_amount", value_cents=200, status="paused"))
    db.commit()

    client = TestClient(app)
    resp = client.get("/v1/admin/discounts", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


def test_update_discount_status(db, tenant: Tenant, auth_headers) -> None:
    disc = Discount(tenant_id=tenant.id, name="Active D", code="ACT",
                    discount_type="percentage", value_bps=500, status="active")
    db.add(disc)
    db.commit()

    client = TestClient(app)
    resp = client.patch(f"/v1/admin/discounts/{disc.id}", json={"status": "paused"},
                        headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"


def test_delete_discount(db, tenant: Tenant, auth_headers) -> None:
    disc = Discount(tenant_id=tenant.id, name="Doomed", code="DOOM",
                    discount_type="percentage", value_bps=100, status="active")
    db.add(disc)
    db.commit()

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/discounts/{disc.id}", headers=auth_headers)
    assert resp.status_code == 204


def test_duplicate_code_rejected(db, tenant: Tenant, auth_headers) -> None:
    db.add(Discount(tenant_id=tenant.id, name="First", code="DUP",
                    discount_type="percentage", value_bps=500, status="active"))
    db.commit()

    client = TestClient(app)
    resp = client.post("/v1/admin/discounts", json={
        "name": "Second", "code": "DUP",
        "discount_type": "percentage", "value_bps": 100,
    }, headers=auth_headers)
    assert resp.status_code == 409


def test_percentage_discount_requires_value_bps(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/discounts", json={
        "name": "Bad", "code": "BAD",
        "discount_type": "percentage",
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert "value_bps" in resp.json()["detail"].lower()
```

Create `services/api/tests/routers/test_discount_apply.py`:

```python
# NOTE: `from __future__ import annotations` deliberately absent.

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, Discount, InventoryPool, InventoryPoolShop, Shop, Tenant


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
    )
    db.add(channel)
    db.flush()

    disc = Discount(
        tenant_id=tenant.id, name="10% off", code="TEN",
        discount_type="percentage", value_bps=1000, status="active",
    )
    db.add(disc)
    db.commit()

    return {"channel": channel, "discount": disc}


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


def test_apply_discount_endpoint(db, tenant: Tenant, setup, auth) -> None:
    client = TestClient(app)
    resp = client.post("/v1/discounts/apply", json={
        "channel_id": str(setup["channel"].id),
        "code": "TEN",
        "cart_subtotal_cents": 10000,
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["discount_amount_cents"] == 1000
    assert body["final_total_cents"] == 9000
    assert body["is_free_shipping"] is False


def test_apply_unknown_code_returns_404(db, tenant: Tenant, setup, auth) -> None:
    client = TestClient(app)
    resp = client.post("/v1/discounts/apply", json={
        "channel_id": str(setup["channel"].id),
        "code": "NOPE",
        "cart_subtotal_cents": 10000,
    })
    assert resp.status_code == 404


def test_apply_ineligible_discount_returns_422(db, tenant: Tenant, setup, auth) -> None:
    """Min subtotal condition not met → structured error."""
    disc2 = Discount(
        tenant_id=tenant.id, name="High min", code="HIGHMIN",
        discount_type="percentage", value_bps=500, status="active",
        min_subtotal_cents=50000,
    )
    db.add(disc2)
    db.commit()

    client = TestClient(app)
    resp = client.post("/v1/discounts/apply", json={
        "channel_id": str(setup["channel"].id),
        "code": "HIGHMIN",
        "cart_subtotal_cents": 1000,
    })
    assert resp.status_code == 422
    assert "minimum" in resp.json()["detail"].lower()
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/routers/test_admin_discounts.py $CONTAINER:/app/tests/routers/test_admin_discounts.py
docker cp services/api/tests/routers/test_discount_apply.py $CONTAINER:/app/tests/routers/test_discount_apply.py
docker compose exec api python -m pytest tests/routers/test_admin_discounts.py tests/routers/test_discount_apply.py -v
docker compose exec api rm -f /app/tests/routers/test_admin_discounts.py /app/tests/routers/test_discount_apply.py
```
Expected: FAIL — router doesn't exist.

- [ ] **Step 3: Implement the router**

Create `services/api/app/routers/admin_discounts.py`:

```python
"""Admin endpoints for discounts + the public discount-apply endpoint.

Admin CRUD requires `discounts:manage` permission.
The apply endpoint is public (no permission gate) — consumed by headless
frontends and hosted checkout.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Discount, DiscountUse
from app.services.discount_service import (
    DiscountNotEligibleError, DiscountNotFoundError, apply_discount,
)

router = APIRouter(tags=["Admin Discounts"])

_VALID_TYPES = {"percentage", "fixed_amount", "free_shipping"}
_VALID_STATUSES = {"active", "paused", "scheduled"}


# ── Schemas ──

class DiscountIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, min_length=1, max_length=128)
    discount_type: str
    value_bps: int | None = Field(default=None, ge=1, le=10000)
    value_cents: int | None = Field(default=None, ge=1)
    channel_id: UUID | None = None
    status: str = "active"
    stackable: bool = False
    priority: int = 0
    min_subtotal_cents: int | None = Field(default=None, ge=0)
    max_uses_total: int | None = Field(default=None, ge=1)
    max_uses_per_customer: int | None = Field(default=None, ge=1)
    starts_at: datetime | None = None
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def _validate_type_and_value(self) -> "DiscountIn":
        if self.discount_type not in _VALID_TYPES:
            raise ValueError(f"discount_type must be one of {sorted(_VALID_TYPES)}")
        if self.discount_type == "percentage" and not self.value_bps:
            raise ValueError("value_bps is required for percentage discounts")
        if self.discount_type == "fixed_amount" and not self.value_cents:
            raise ValueError("value_cents is required for fixed_amount discounts")
        return self


class DiscountPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = None
    stackable: bool | None = None
    priority: int | None = None
    min_subtotal_cents: int | None = None
    max_uses_total: int | None = None
    max_uses_per_customer: int | None = None
    starts_at: datetime | None = None
    expires_at: datetime | None = None


class DiscountOut(BaseModel):
    id: UUID
    tenant_id: UUID
    channel_id: UUID | None
    name: str
    code: str | None
    discount_type: str
    value_bps: int | None
    value_cents: int | None
    status: str
    stackable: bool
    priority: int
    min_subtotal_cents: int | None
    max_uses_total: int | None
    max_uses_per_customer: int | None
    starts_at: datetime | None
    expires_at: datetime | None
    times_used: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DiscountApplyIn(BaseModel):
    channel_id: UUID
    code: str | None = None
    cart_subtotal_cents: int = Field(ge=0)
    customer_id: UUID | None = None


# ── Helpers ──

def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator not assigned to a tenant",
        )
    return ctx.tenant_id


def _get_discount_or_404(db: Session, discount_id: UUID, tenant_id: UUID) -> Discount:
    d = db.get(Discount, discount_id)
    if d is None or d.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Discount not found")
    return d


def _times_used(db: Session, discount_id: UUID) -> int:
    return db.execute(
        select(func.count(DiscountUse.id)).where(DiscountUse.discount_id == discount_id)
    ).scalar_one()


def _to_out(db: Session, d: Discount) -> DiscountOut:
    return DiscountOut(
        id=d.id, tenant_id=d.tenant_id, channel_id=d.channel_id,
        name=d.name, code=d.code, discount_type=d.discount_type,
        value_bps=d.value_bps, value_cents=d.value_cents,
        status=d.status, stackable=d.stackable, priority=d.priority,
        min_subtotal_cents=d.min_subtotal_cents,
        max_uses_total=d.max_uses_total, max_uses_per_customer=d.max_uses_per_customer,
        starts_at=d.starts_at, expires_at=d.expires_at,
        times_used=_times_used(db, d.id),
        created_at=d.created_at, updated_at=d.updated_at,
    )


# ── Admin routes ──

@router.get(
    "/v1/admin/discounts",
    response_model=list[DiscountOut],
    dependencies=[require_permission("discounts:manage")],
)
def list_discounts(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[DiscountOut]:
    tenant_id = _require_tenant(ctx)
    rows = db.execute(
        select(Discount).where(Discount.tenant_id == tenant_id)
        .order_by(Discount.priority.desc(), Discount.name)
    ).scalars().all()
    return [_to_out(db, r) for r in rows]


@router.post(
    "/v1/admin/discounts",
    response_model=DiscountOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission("discounts:manage")],
)
def create_discount(
    body: DiscountIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> DiscountOut:
    tenant_id = _require_tenant(ctx)

    if body.status not in _VALID_STATUSES:
        raise HTTPException(status_code=400,
                            detail=f"status must be one of {sorted(_VALID_STATUSES)}")

    disc = Discount(
        tenant_id=tenant_id,
        channel_id=body.channel_id,
        name=body.name,
        code=body.code.upper() if body.code else None,
        discount_type=body.discount_type,
        value_bps=body.value_bps,
        value_cents=body.value_cents,
        status=body.status,
        stackable=body.stackable,
        priority=body.priority,
        min_subtotal_cents=body.min_subtotal_cents,
        max_uses_total=body.max_uses_total,
        max_uses_per_customer=body.max_uses_per_customer,
        starts_at=body.starts_at,
        expires_at=body.expires_at,
    )
    db.add(disc)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A discount with code {body.code!r} already exists for this tenant",
        )
    db.refresh(disc)
    return _to_out(db, disc)


@router.patch(
    "/v1/admin/discounts/{discount_id}",
    response_model=DiscountOut,
    dependencies=[require_permission("discounts:manage")],
)
def update_discount(
    discount_id: UUID,
    body: DiscountPatch,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> DiscountOut:
    tenant_id = _require_tenant(ctx)
    disc = _get_discount_or_404(db, discount_id, tenant_id)

    updates = body.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] not in _VALID_STATUSES:
        raise HTTPException(status_code=400,
                            detail=f"status must be one of {sorted(_VALID_STATUSES)}")
    for field, value in updates.items():
        setattr(disc, field, value)

    db.commit()
    db.refresh(disc)
    return _to_out(db, disc)


@router.delete(
    "/v1/admin/discounts/{discount_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission("discounts:manage")],
)
def delete_discount(
    discount_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    disc = _get_discount_or_404(db, discount_id, tenant_id)
    db.delete(disc)
    db.commit()


# ── Public apply ──

@router.post("/v1/discounts/apply")
def apply(
    body: DiscountApplyIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> dict[str, Any]:
    """Public discount calculator. Validates and computes discount amount.

    Returns 404 if the code doesn't exist or is inactive.
    Returns 422 if the code exists but conditions aren't met.
    Does NOT write a DiscountUse row — the caller commits use after payment.
    """
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Operator not assigned to a tenant")

    try:
        return apply_discount(
            db,
            tenant_id=ctx.tenant_id,
            channel_id=body.channel_id,
            code=body.code,
            cart_subtotal_cents=body.cart_subtotal_cents,
            customer_id=body.customer_id,
        )
    except DiscountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except DiscountNotEligibleError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
```

- [ ] **Step 4: Mount the router**

In `services/api/app/main.py`, add `admin_discounts` to the imports (alphabetically between `admin_catalog` and `admin_customers`) and add `app.include_router(admin_discounts.router)`.

- [ ] **Step 5: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/main.py $CONTAINER:/app/app/main.py
docker cp services/api/app/routers/admin_discounts.py $CONTAINER:/app/app/routers/admin_discounts.py
docker cp services/api/app/services/discount_service.py $CONTAINER:/app/app/services/discount_service.py
docker cp services/api/tests $CONTAINER:/app/tests
docker compose restart api
sleep 5
docker compose exec api python -m pytest \
  tests/routers/test_admin_discounts.py \
  tests/routers/test_discount_apply.py \
  tests/test_admin_console_contracts.py::test_discount_out_schema \
  -v
docker compose exec api rm -rf /app/tests
```
Expected: 8 admin tests + 3 apply tests + 1 contract test = 12 passed.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/routers/admin_discounts.py \
        services/api/app/main.py \
        services/api/tests/routers/test_admin_discounts.py \
        services/api/tests/routers/test_discount_apply.py
git commit -m "feat(discounts): admin CRUD + POST /v1/discounts/apply"
```

---

### Task 4: Integration smoke test

**Files:**
- Create: `services/api/tests/integration/test_discounts_e2e.py`

- [ ] **Step 1: Write integration test**

Create `services/api/tests/integration/test_discounts_e2e.py`:

```python
"""End-to-end smoke test for the discounts module."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, InventoryPool, InventoryPoolShop, Shop, Tenant


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
def auth(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id,
        role="owner", role_id=None, is_legacy_token=False,
        permissions=frozenset({"discounts:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield
    app.dependency_overrides.clear()


def _apply(client, channel_id, code, subtotal=10000):
    return client.post("/v1/discounts/apply", json={
        "channel_id": str(channel_id),
        "code": code,
        "cart_subtotal_cents": subtotal,
    })


def test_create_and_apply_percentage(db, tenant: Tenant, channel: Channel, auth) -> None:
    client = TestClient(app)

    resp = client.post("/v1/admin/discounts", json={
        "name": "20% off", "code": "TWENTY",
        "discount_type": "percentage", "value_bps": 2000,
    })
    assert resp.status_code == 201
    assert resp.json()["times_used"] == 0

    apply_resp = _apply(client, channel.id, "TWENTY", subtotal=10000)
    assert apply_resp.status_code == 200
    body = apply_resp.json()
    assert body["discount_amount_cents"] == 2000
    assert body["final_total_cents"] == 8000
    assert body["is_free_shipping"] is False


def test_create_and_apply_free_shipping(db, tenant: Tenant, channel: Channel, auth) -> None:
    client = TestClient(app)

    client.post("/v1/admin/discounts", json={
        "name": "Free Ship", "code": "FREESHIP", "discount_type": "free_shipping",
    })

    apply_resp = _apply(client, channel.id, "FREESHIP", subtotal=5000)
    assert apply_resp.status_code == 200
    assert apply_resp.json()["is_free_shipping"] is True
    assert apply_resp.json()["discount_amount_cents"] == 0


def test_paused_discount_not_applicable(db, tenant: Tenant, channel: Channel, auth) -> None:
    client = TestClient(app)

    resp = client.post("/v1/admin/discounts", json={
        "name": "Was Active", "code": "PAUSE_ME",
        "discount_type": "percentage", "value_bps": 1000,
    })
    disc_id = resp.json()["id"]

    # Pause it
    client.patch(f"/v1/admin/discounts/{disc_id}", json={"status": "paused"})

    # Apply should return 404
    apply_resp = _apply(client, channel.id, "PAUSE_ME")
    assert apply_resp.status_code == 404


def test_min_subtotal_not_met(db, tenant: Tenant, channel: Channel, auth) -> None:
    client = TestClient(app)

    client.post("/v1/admin/discounts", json={
        "name": "Min 500", "code": "MIN500",
        "discount_type": "percentage", "value_bps": 1000,
        "min_subtotal_cents": 50000,
    })

    apply_resp = _apply(client, channel.id, "MIN500", subtotal=10000)
    assert apply_resp.status_code == 422
    assert "minimum" in apply_resp.json()["detail"].lower()


def test_discount_lifecycle(db, tenant: Tenant, channel: Channel, auth) -> None:
    """Create, list, update, delete — admin management lifecycle."""
    client = TestClient(app)

    # Create
    create = client.post("/v1/admin/discounts", json={
        "name": "Lifecycle Test", "code": "LIFE",
        "discount_type": "fixed_amount", "value_cents": 300,
    })
    assert create.status_code == 201
    disc_id = create.json()["id"]

    # List includes it
    list_resp = client.get("/v1/admin/discounts")
    assert any(d["id"] == disc_id for d in list_resp.json())

    # Patch name
    patch = client.patch(f"/v1/admin/discounts/{disc_id}", json={"name": "Renamed"})
    assert patch.status_code == 200
    assert patch.json()["name"] == "Renamed"

    # Delete
    del_resp = client.delete(f"/v1/admin/discounts/{disc_id}")
    assert del_resp.status_code == 204

    # Gone from list
    list_after = client.get("/v1/admin/discounts")
    assert not any(d["id"] == disc_id for d in list_after.json())
```

- [ ] **Step 2: Run integration test**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest tests/integration/test_discounts_e2e.py -v
docker compose exec api rm -rf /app/tests
```
Expected: 5 passed.

- [ ] **Step 3: Run full discounts suite**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest \
  tests/services/test_discount_service.py \
  tests/routers/test_admin_discounts.py \
  tests/routers/test_discount_apply.py \
  tests/integration/test_discounts_e2e.py \
  tests/test_admin_console_contracts.py::test_discount_out_schema \
  -v 2>&1 | tail -5
docker compose exec api rm -rf /app/tests
```
Expected ballpark: ~29 tests passing.

- [ ] **Step 4: Commit**

```bash
git add services/api/tests/integration/test_discounts_e2e.py
git commit -m "test(discounts): end-to-end smoke test for discount lifecycle"
```

---

## Done. Summary of what shipped

- New tables `discounts` and `discount_uses` with RLS, indexes, `discounts:manage` permission
- `app/services/discount_service.py` — `apply_discount` with full eligibility chain (window, min subtotal, global limit, per-customer limit), `record_discount_use` ledger writer
- `app/routers/admin_discounts.py` — discount CRUD (list/create/patch/delete) + `POST /v1/discounts/apply`
- ~29 tests across services, admin CRUD, apply endpoint, and E2E

## What this unlocks

- **Hosted checkout** (Phase 2): merchants can offer coupon codes at checkout; shoppers enter a code, the hosted checkout calls `/v1/discounts/apply`, and the discount is shown before payment
- **Headless storefront API**: same pattern — custom sites call the apply endpoint in their cart UI
- The apply→shipping→tax pipeline is now complete: apply discount → recompute shipping eligibility (post-discount subtotal) → compute tax on discounted amount

## Follow-up work (not in this plan)

- Buy-X-get-Y offer type (Domain 56 — Advanced Promotions)
- Product-specific / category-specific discount conditions
- Discount stacking (multiple discounts on one cart)
- Loyalty multiplier events (Domain 56)
- Automatic cleanup sweep of cart-token DiscountUse rows when carts are abandoned

---

*End of plan.*
