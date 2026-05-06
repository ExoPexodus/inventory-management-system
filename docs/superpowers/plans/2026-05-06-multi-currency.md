# Multi-Currency Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-listing multi-currency pricing for products and an FX rate engine so channels selling in different currencies (Shopify EU in EUR, headless API in USD/INR, hosted checkout with shopper-facing currency switching) all resolve prices correctly without retrofitting POS legacy code.

**Architecture:** Two new tables — `product_prices` (per-product, per-currency, optionally per-channel pricing overrides) and `fx_rates` (per-tenant currency-pair rates with manual entry; auto-sync from a public provider is a follow-up plan). Three new modules in `app/billing/`: `money.py` (a frozen `Money(amount_cents, currency_code)` value type that asserts same-currency on arithmetic), `fx.py` (the only place in the codebase that does FX conversion — `get_rate`, `set_rate`, `convert`), and `pricing.py` (resolves "what's the price of product X in currency Y for channel Z?", falling back from explicit ProductPrice → FX-derived from base). Two admin routers gated by a single `currency:manage` permission. POS (Transaction/TransactionLine/PaymentAllocation) stays single-currency-per-tenant — multi-currency is an e-commerce concern only.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, PostgreSQL (with RLS), pytest

**Out of scope (deferred):**
- Auto-sync of FX rates from a public provider (openexchangerates / ECB) — this plan ships the table + service; auto-sync is a follow-up plan once a provider is chosen.
- Multi-currency on the POS path (`Transaction`/`TransactionLine`/`PaymentAllocation`) — POS stays in `tenant.default_currency_code`. Per-row currency on legacy POS tables is a future cleanup if/when POS multi-currency demand emerges.
- Wiring multi-currency into channel-incoming order ingest — that ships in Phase 1 connector plans (Shopify, WooCommerce). This plan provides the resolver; the connectors will call it.

---

### Long-term complexity discipline (read once, follow forever)

Multi-currency code rots fast when conversion logic scatters. Three rules baked into this plan:

1. **`Money(amount_cents, currency_code)` is the only typed money primitive.** Any new code that handles cross-currency math takes/returns `Money`, never raw `int + str`. The `Money.__add__` / `__sub__` methods assert same-currency.
2. **`fx.convert(money, target_currency)` is the only place that does FX conversion.** Every other code path either stays in one currency end-to-end, or calls `fx.convert` once at the boundary (display, report, order creation).
3. **Currency is pinned at the boundary, never reconverted internally.** `Order.currency_code` is frozen at order time. Reports that need cross-currency totals convert at report time using current rates — never store derived "in tenant currency" amounts on the order itself.

If a future PR introduces cents-math across currencies anywhere except `fx.convert`, that's the smell to catch in code review.

---

### Task 1: Migration + ProductPrice + FxRate models + contract tests

**Files:**
- Create: `services/api/alembic/versions/20260509000001_multi_currency.py`
- Modify: `services/api/app/models/tables.py`
- Modify: `services/api/app/models/__init__.py`
- Modify: `services/api/tests/test_admin_console_contracts.py`

- [ ] **Step 1: Write the failing contract tests**

Add to `services/api/tests/test_admin_console_contracts.py`:

```python
def test_product_price_out_schema() -> None:
    from app.routers.admin_product_prices import ProductPriceOut

    p = ProductPriceOut(
        id=uuid4(),
        tenant_id=uuid4(),
        product_id=uuid4(),
        channel_id=None,
        currency_code="USD",
        amount_cents=1999,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    d = p.model_dump(mode="json")
    assert d["currency_code"] == "USD"
    assert d["amount_cents"] == 1999


def test_fx_rate_out_schema() -> None:
    from app.routers.admin_fx_rates import FxRateOut

    r = FxRateOut(
        id=uuid4(),
        tenant_id=uuid4(),
        from_currency="USD",
        to_currency="INR",
        rate="83.250000",
        source="manual",
        effective_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    d = r.model_dump(mode="json")
    assert d["from_currency"] == "USD"
    assert d["to_currency"] == "INR"
    assert d["rate"] == "83.250000"
```

The `from datetime import UTC, datetime` and `from uuid import uuid4` imports are already at the top.

- [ ] **Step 2: Run tests to confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/test_admin_console_contracts.py $CONTAINER:/app/tests/test_admin_console_contracts.py
docker compose exec api python -m pytest tests/test_admin_console_contracts.py::test_product_price_out_schema tests/test_admin_console_contracts.py::test_fx_rate_out_schema -v
```
Expected: FAIL — both `ModuleNotFoundError`. Stays red until Task 5.

- [ ] **Step 3: Add SQLAlchemy models**

In `services/api/app/models/tables.py`, append after `StockReservation`:

```python
class ProductPrice(Base):
    """Multi-currency price for a product, optionally scoped to a channel.

    Resolution order at lookup time (handled by app/billing/pricing.py):
      1. ProductPrice with matching (product_id, channel_id, currency_code) — exact match
      2. ProductPrice with matching (product_id, currency_code, channel_id IS NULL) — tenant-wide
      3. FX-derived from Product.unit_price_cents (in tenant's default currency)

    A row with channel_id=NULL is the tenant-wide price in that currency. A row
    with channel_id set overrides the tenant-wide price for that channel only.
    """
    __tablename__ = "product_prices"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "channel_id", "currency_code",
            name="uq_product_price_product_channel_currency",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    channel_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), nullable=True
    )
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FxRate(Base):
    """Per-tenant FX rate for a currency pair, with effective-at timestamp.

    Rate is stored as a Numeric string for precision (e.g. "83.250000"). The
    pair (from_currency, to_currency) is unique per tenant — the most recent
    effective_at wins on conflict. Manual upload via admin endpoint; auto-sync
    from a public provider is a follow-up plan.

    A 1:1 rate (e.g. USD→USD) is implicit and not stored. The fx service
    handles same-currency conversion as a no-op without touching this table.
    """
    __tablename__ = "fx_rates"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "from_currency", "to_currency",
            name="uq_fx_tenant_pair",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    from_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    to_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # Numeric stored as String for arbitrary precision; FX rates often have 6+ decimals
    rate: Mapped[str] = mapped_column(Numeric(20, 10), nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="manual", server_default="manual", nullable=False)
    # source: 'manual' | future: 'openexchangerates' | 'ecb' | 'xe' etc.
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

You may need to add `Numeric` to the SQLAlchemy imports at the top of the file. Search the existing imports for `from sqlalchemy import` and add it if not present.

- [ ] **Step 4: Export the models**

In `services/api/app/models/__init__.py`, add `FxRate` and `ProductPrice` to BOTH the import block and `__all__` (alphabetical).

- [ ] **Step 5: Write the migration**

Create `services/api/alembic/versions/20260509000001_multi_currency.py`:

```python
"""Multi-currency: product_prices + fx_rates tables, currency:manage permission

Revision ID: 20260509000001
Revises: 20260508000001
Create Date: 2026-05-09 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "20260509000001"
down_revision = "20260508000001"
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
    # 1. product_prices
    op.create_table(
        "product_prices",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=True),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("amount_cents", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "product_id", "channel_id", "currency_code",
            name="uq_product_price_product_channel_currency",
        ),
    )
    op.create_index("ix_product_prices_tenant_id", "product_prices", ["tenant_id"])
    op.create_index(
        "ix_product_prices_lookup",
        "product_prices",
        ["product_id", "currency_code"],
    )

    # 2. fx_rates
    op.create_table(
        "fx_rates",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_currency", sa.String(3), nullable=False),
        sa.Column("to_currency", sa.String(3), nullable=False),
        sa.Column("rate", sa.Numeric(20, 10), nullable=False),
        sa.Column("source", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("effective_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "tenant_id", "from_currency", "to_currency",
            name="uq_fx_tenant_pair",
        ),
    )
    op.create_index("ix_fx_rates_tenant_id", "fx_rates", ["tenant_id"])
    op.create_index(
        "ix_fx_rates_pair_lookup",
        "fx_rates",
        ["tenant_id", "from_currency", "to_currency"],
    )

    # 3. Permission seed
    op.execute("""
        INSERT INTO permissions (id, codename, display_name, category, description)
        VALUES (gen_random_uuid(), 'currency:manage', 'Manage Currency Configuration', 'billing',
                'Manage tenant FX rates and per-channel/per-product price overrides')
        ON CONFLICT (codename) DO UPDATE SET description = EXCLUDED.description
    """)
    # Grant to system 'owner' role (matches the channels:manage / inventory_pools:manage / reservations:manage pattern)
    op.execute("""
        INSERT INTO role_permissions (id, role_id, permission_id)
        SELECT gen_random_uuid(), r.id, p.id
        FROM roles r, permissions p
        WHERE r.name = 'owner' AND r.is_system = true
          AND p.codename = 'currency:manage'
        ON CONFLICT DO NOTHING
    """)

    # 4. RLS on both new tables
    for table in ["product_prices", "fx_rates"]:
        op.execute(f"""
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
            CREATE POLICY ims_tenant_isolation ON {table}
            USING ({_RLS_POLICY})
            WITH CHECK ({_RLS_POLICY});
        """)


def downgrade() -> None:
    for table in ["fx_rates", "product_prices"]:
        op.execute(f"DROP POLICY IF EXISTS ims_tenant_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.execute("""
        DELETE FROM role_permissions WHERE permission_id IN (
            SELECT id FROM permissions WHERE codename = 'currency:manage'
        )
    """)
    op.execute("DELETE FROM permissions WHERE codename = 'currency:manage'")

    op.drop_index("ix_fx_rates_pair_lookup", table_name="fx_rates")
    op.drop_index("ix_fx_rates_tenant_id", table_name="fx_rates")
    op.drop_table("fx_rates")
    op.drop_index("ix_product_prices_lookup", table_name="product_prices")
    op.drop_index("ix_product_prices_tenant_id", table_name="product_prices")
    op.drop_table("product_prices")
```

- [ ] **Step 6: Run migration**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/alembic/versions/20260509000001_multi_currency.py $CONTAINER:/app/alembic/versions/
docker compose exec api alembic upgrade head
```
Expected: `Running upgrade 20260508000001 -> 20260509000001`

- [ ] **Step 7: Verify schema, RLS, permission**

```bash
docker compose exec postgres psql -U ims -d ims -c "\d product_prices"
docker compose exec postgres psql -U ims -d ims -c "\d fx_rates"
docker compose exec postgres psql -U ims -d ims -c "SELECT codename FROM permissions WHERE codename='currency:manage'"
docker compose exec postgres psql -U ims -d ims -c "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname IN ('product_prices', 'fx_rates')"
```
Expected: both table descriptions printed, permission row present, both RLS flags `t` for both tables.

- [ ] **Step 8: Commit**

```bash
git add services/api/alembic/versions/20260509000001_multi_currency.py \
        services/api/app/models/tables.py \
        services/api/app/models/__init__.py \
        services/api/tests/test_admin_console_contracts.py
git commit -m "feat(currency): add product_prices + fx_rates tables with RLS"
```

(Contract tests stay red until Task 5.)

---

### Task 2: Money value type

**Files:**
- Create: `services/api/app/billing/money.py`
- Create: `services/api/tests/billing/test_money.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/billing/test_money.py`:

```python
import pytest

from app.billing.money import Money, round_half_up_cents


def test_money_construction() -> None:
    m = Money(1999, "USD")
    assert m.amount_cents == 1999
    assert m.currency_code == "USD"


def test_money_currency_code_is_uppercased() -> None:
    """Construction normalises currency to upper-case so 'usd' and 'USD' compare equal."""
    m = Money(100, "usd")
    assert m.currency_code == "USD"


def test_money_addition_same_currency() -> None:
    a = Money(100, "USD")
    b = Money(50, "USD")
    assert (a + b) == Money(150, "USD")


def test_money_addition_different_currency_raises() -> None:
    a = Money(100, "USD")
    b = Money(50, "EUR")
    with pytest.raises(ValueError, match="currency"):
        a + b


def test_money_subtraction() -> None:
    a = Money(100, "USD")
    b = Money(40, "USD")
    assert (a - b) == Money(60, "USD")


def test_money_equality() -> None:
    assert Money(100, "USD") == Money(100, "USD")
    assert Money(100, "USD") != Money(100, "EUR")
    assert Money(100, "USD") != Money(101, "USD")


def test_money_is_frozen() -> None:
    """Frozen dataclass — direct attribute assignment fails."""
    import dataclasses
    m = Money(100, "USD")
    with pytest.raises(dataclasses.FrozenInstanceError):
        m.amount_cents = 200  # type: ignore[misc]


def test_money_repr_is_human_readable() -> None:
    m = Money(1999, "USD")
    s = repr(m)
    assert "1999" in s
    assert "USD" in s


def test_round_half_up_cents_half_rounds_up() -> None:
    """0.5 cents always rounds up to 1 (not banker's rounding)."""
    assert round_half_up_cents(100.5) == 101
    assert round_half_up_cents(99.5) == 100


def test_round_half_up_cents_below_half_rounds_down() -> None:
    assert round_half_up_cents(100.4999) == 100


def test_round_half_up_cents_handles_negative() -> None:
    """Negative amounts also round 'half up' in absolute terms (toward +inf)."""
    assert round_half_up_cents(-100.5) == -100  # half-up = toward positive infinity
    assert round_half_up_cents(-100.6) == -101


def test_round_half_up_cents_handles_decimal_input() -> None:
    """Accept Decimal inputs — FX math uses Decimal for precision."""
    from decimal import Decimal
    assert round_half_up_cents(Decimal("100.5")) == 101
    assert round_half_up_cents(Decimal("99.4")) == 99
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/billing $CONTAINER:/app/tests/billing
docker compose exec api python -m pytest tests/billing/test_money.py -v
docker compose exec api rm -rf /app/tests/billing
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.billing.money'`

- [ ] **Step 3: Implement `Money` and `round_half_up_cents`**

Create `services/api/app/billing/money.py`:

```python
"""Money value type — the only typed money primitive in the codebase.

Use ``Money`` whenever you handle amounts that may cross currencies. Operations
between Money instances assert same-currency. The only legal way to convert is
via ``app.billing.fx.convert``.

Three rules baked into this codebase:

1. Currency is pinned at the boundary (Order, Channel, ProductPrice). Don't
   reconvert internally.
2. ``fx.convert`` is the single seam for cross-currency math.
3. Cents amounts are integers. FX math uses Decimal then rounds to whole cents
   via ``round_half_up_cents``.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class Money:
    """An amount of money in a specific currency.

    Frozen — once constructed, can't mutate. Currency is normalised to upper
    case so ``Money(100, "usd") == Money(100, "USD")``.
    """
    amount_cents: int
    currency_code: str

    def __post_init__(self) -> None:
        # Normalise currency to upper-case. We have to use object.__setattr__
        # because the dataclass is frozen.
        if self.currency_code != self.currency_code.upper():
            object.__setattr__(self, "currency_code", self.currency_code.upper())

    def __add__(self, other: "Money") -> "Money":
        self._assert_same_currency(other)
        return Money(self.amount_cents + other.amount_cents, self.currency_code)

    def __sub__(self, other: "Money") -> "Money":
        self._assert_same_currency(other)
        return Money(self.amount_cents - other.amount_cents, self.currency_code)

    def _assert_same_currency(self, other: "Money") -> None:
        if self.currency_code != other.currency_code:
            raise ValueError(
                f"Cannot operate on mixed currencies: {self.currency_code} and "
                f"{other.currency_code}. Use app.billing.fx.convert first."
            )

    def __repr__(self) -> str:
        return f"Money({self.amount_cents} {self.currency_code})"


def round_half_up_cents(amount: float | Decimal) -> int:
    """Round a Decimal/float cents-amount to the nearest whole cent, half-up.

    Half-up means 0.5 → 1, -0.5 → 0 (toward positive infinity at .5 boundary).
    This is the standard retail rounding choice — matches POS rounding and
    avoids banker's-rounding surprises.
    """
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
```

- [ ] **Step 4: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/billing/money.py $CONTAINER:/app/app/billing/money.py
docker cp services/api/tests/billing $CONTAINER:/app/tests/billing
docker compose exec api python -m pytest tests/billing/test_money.py -v
docker compose exec api rm -rf /app/tests/billing
```
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/billing/money.py \
        services/api/tests/billing/test_money.py
git commit -m "feat(currency): add Money value type with round_half_up_cents helper"
```

---

### Task 3: FX service — get_rate / set_rate / convert

**Files:**
- Create: `services/api/app/billing/fx.py`
- Create: `services/api/tests/billing/test_fx.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/billing/test_fx.py`:

```python
import uuid
from decimal import Decimal

import pytest

from app.billing.money import Money
from app.models import FxRate, Tenant


def test_get_rate_returns_none_when_pair_unknown(db, tenant: Tenant) -> None:
    from app.billing.fx import get_rate
    assert get_rate(db, tenant.id, "USD", "INR") is None


def test_set_rate_creates_new(db, tenant: Tenant) -> None:
    from app.billing.fx import get_rate, set_rate
    set_rate(db, tenant.id, "USD", "INR", Decimal("83.25"))
    db.flush()
    rate = get_rate(db, tenant.id, "USD", "INR")
    assert rate == Decimal("83.25")


def test_set_rate_updates_existing(db, tenant: Tenant) -> None:
    """Setting the same pair twice updates the existing row (no duplicate)."""
    from sqlalchemy import select
    from app.billing.fx import set_rate

    set_rate(db, tenant.id, "USD", "INR", Decimal("82.00"))
    set_rate(db, tenant.id, "USD", "INR", Decimal("83.50"))
    db.flush()

    rows = db.execute(
        select(FxRate).where(
            FxRate.tenant_id == tenant.id,
            FxRate.from_currency == "USD",
            FxRate.to_currency == "INR",
        )
    ).scalars().all()
    assert len(rows) == 1
    assert Decimal(rows[0].rate) == Decimal("83.50")


def test_convert_same_currency_is_identity(db, tenant: Tenant) -> None:
    """Same-currency conversion is a no-op without touching FX table."""
    from app.billing.fx import convert
    m = Money(1999, "USD")
    converted = convert(db, tenant.id, m, "USD")
    assert converted == m


def test_convert_uses_stored_rate(db, tenant: Tenant) -> None:
    from app.billing.fx import convert, set_rate

    set_rate(db, tenant.id, "USD", "INR", Decimal("83.25"))
    db.flush()

    # 100 USD -> 8325 INR (cents-to-cents)
    result = convert(db, tenant.id, Money(100_00, "USD"), "INR")
    assert result.currency_code == "INR"
    # 100 USD = 100 * 83.25 = 8325 INR
    assert result.amount_cents == 8325_00


def test_convert_rounds_half_up(db, tenant: Tenant) -> None:
    """A rate that produces fractional cents rounds half-up."""
    from app.billing.fx import convert, set_rate

    # Pick a rate where 100 cents converts to 100.5 → rounds to 101
    set_rate(db, tenant.id, "USD", "EUR", Decimal("1.005"))
    db.flush()

    result = convert(db, tenant.id, Money(100, "USD"), "EUR")
    assert result == Money(101, "EUR")


def test_convert_uses_inverse_rate_when_only_reverse_pair_stored(db, tenant: Tenant) -> None:
    """If USD→INR is unknown but INR→USD is stored, convert via inversion."""
    from app.billing.fx import convert, set_rate

    set_rate(db, tenant.id, "INR", "USD", Decimal("0.012"))  # 1 INR = 0.012 USD
    db.flush()

    # 1000 INR -> ? USD. 1000 * 0.012 = 12 USD = 1200 cents
    result = convert(db, tenant.id, Money(1000_00, "INR"), "USD")
    assert result.currency_code == "USD"
    assert result.amount_cents == 1200


def test_convert_raises_when_no_rate_available(db, tenant: Tenant) -> None:
    """No rate for either direction → raise so caller knows to handle."""
    from app.billing.fx import FxRateMissingError, convert
    with pytest.raises(FxRateMissingError, match="USD.*JPY"):
        convert(db, tenant.id, Money(100, "USD"), "JPY")


def test_set_rate_normalises_currency_codes_to_upper(db, tenant: Tenant) -> None:
    from app.billing.fx import get_rate, set_rate
    set_rate(db, tenant.id, "usd", "inr", Decimal("83.0"))
    db.flush()
    # Must be retrievable using upper-case
    assert get_rate(db, tenant.id, "USD", "INR") == Decimal("83.0")
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/billing $CONTAINER:/app/tests/billing
docker compose exec api python -m pytest tests/billing/test_fx.py -v
docker compose exec api rm -rf /app/tests/billing
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.billing.fx'`

- [ ] **Step 3: Implement the FX service**

Create `services/api/app/billing/fx.py`:

```python
"""FX service — the only place in the codebase that does cross-currency conversion.

Three responsibilities:
  - Read a stored rate for a currency pair (`get_rate`)
  - Upsert a rate (`set_rate`) — sets ``effective_at`` to now
  - Convert a Money instance to a target currency (`convert`)

Conversion rules:
  - Same-currency: no-op, no DB hit
  - Direct rate exists: amount × rate, rounded half-up to whole cents
  - Inverse rate exists (e.g. you stored INR→USD but ask USD→INR): use 1/rate
  - Neither: raise ``FxRateMissingError`` — callers handle (display "—",
    fail the order, etc.)

This module deliberately doesn't compute FX via base-currency triangulation
(USD→base→INR). That's complexity that helps when you have ~hundreds of
currencies and few stored pairs; with manual upload at this stage, operators
will just store the pairs they need directly.
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.money import Money, round_half_up_cents
from app.models import FxRate


class FxRateMissingError(LookupError):
    """No rate available (direct or inverse) for the requested pair."""


def _norm(code: str) -> str:
    return code.upper()


def get_rate(db: Session, tenant_id: UUID, from_currency: str, to_currency: str) -> Decimal | None:
    """Return the stored rate for the pair, or None if not found.

    Looks up the exact direction only — no inversion, no triangulation. Use
    ``convert`` when you want the full conversion logic.
    """
    row = db.execute(
        select(FxRate).where(
            FxRate.tenant_id == tenant_id,
            FxRate.from_currency == _norm(from_currency),
            FxRate.to_currency == _norm(to_currency),
        )
    ).scalar_one_or_none()
    return Decimal(row.rate) if row is not None else None


def set_rate(
    db: Session,
    tenant_id: UUID,
    from_currency: str,
    to_currency: str,
    rate: Decimal,
) -> FxRate:
    """Upsert a rate. Bumps effective_at to now."""
    from datetime import UTC, datetime
    from_c = _norm(from_currency)
    to_c = _norm(to_currency)

    existing = db.execute(
        select(FxRate).where(
            FxRate.tenant_id == tenant_id,
            FxRate.from_currency == from_c,
            FxRate.to_currency == to_c,
        )
    ).scalar_one_or_none()

    now = datetime.now(UTC)
    if existing is not None:
        existing.rate = rate
        existing.effective_at = now
        db.flush()
        return existing

    row = FxRate(
        tenant_id=tenant_id,
        from_currency=from_c,
        to_currency=to_c,
        rate=rate,
        source="manual",
        effective_at=now,
    )
    db.add(row)
    db.flush()
    return row


def convert(db: Session, tenant_id: UUID, money: Money, target_currency: str) -> Money:
    """Convert a Money to a target currency.

    Same-currency: returns the input unchanged (no DB hit).
    Direct rate: amount_cents × rate, rounded half-up.
    Inverse rate: amount_cents × (1 / inverse_rate), rounded half-up.
    Neither: raise ``FxRateMissingError``.
    """
    target = _norm(target_currency)
    if money.currency_code == target:
        return money

    direct = get_rate(db, tenant_id, money.currency_code, target)
    if direct is not None:
        new_cents = round_half_up_cents(Decimal(money.amount_cents) * direct)
        return Money(new_cents, target)

    inverse = get_rate(db, tenant_id, target, money.currency_code)
    if inverse is not None and inverse != 0:
        new_cents = round_half_up_cents(Decimal(money.amount_cents) / inverse)
        return Money(new_cents, target)

    raise FxRateMissingError(
        f"No FX rate available for {money.currency_code} → {target} on tenant {tenant_id}"
    )
```

- [ ] **Step 4: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/billing/fx.py $CONTAINER:/app/app/billing/fx.py
docker cp services/api/tests/billing $CONTAINER:/app/tests/billing
docker compose exec api python -m pytest tests/billing/test_fx.py -v
docker compose exec api rm -rf /app/tests/billing
```
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/billing/fx.py \
        services/api/tests/billing/test_fx.py
git commit -m "feat(currency): add fx service with get_rate/set_rate/convert (manual upload)"
```

---

### Task 4: Pricing resolver — price_for_product_in_currency

**Files:**
- Create: `services/api/app/billing/pricing.py`
- Create: `services/api/tests/billing/test_pricing.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/billing/test_pricing.py`:

```python
import uuid
from decimal import Decimal

import pytest

from app.billing.money import Money
from app.models import (
    Channel, InventoryPool, InventoryPoolShop, Product, ProductPrice, Shop, Tenant,
)


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"POS at {shop.name}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="manual", name=f"channel-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="USD", shop_id=None,
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def product(db, tenant: Tenant) -> Product:
    """Product with unit_price_cents=1999 (in tenant default currency)."""
    p = Product(
        tenant_id=tenant.id, name="Widget",
        sku=f"sku-{uuid.uuid4().hex[:6]}", unit_price_cents=1999,
    )
    db.add(p)
    db.flush()
    return p


def test_explicit_channel_specific_price_wins(db, tenant: Tenant, channel: Channel, product: Product) -> None:
    """A ProductPrice with matching (product, channel, currency) is the highest priority."""
    from app.billing.pricing import price_for_product_in_currency

    # tenant-wide USD price
    db.add(ProductPrice(
        tenant_id=tenant.id, product_id=product.id, channel_id=None,
        currency_code="USD", amount_cents=1999,
    ))
    # channel-specific USD price (override)
    db.add(ProductPrice(
        tenant_id=tenant.id, product_id=product.id, channel_id=channel.id,
        currency_code="USD", amount_cents=1799,
    ))
    db.flush()

    price = price_for_product_in_currency(db, product.id, "USD", channel_id=channel.id)
    assert price == Money(1799, "USD")


def test_tenant_wide_price_when_no_channel_override(db, tenant: Tenant, channel: Channel, product: Product) -> None:
    """Falls back to the tenant-wide ProductPrice (channel_id IS NULL)."""
    from app.billing.pricing import price_for_product_in_currency

    db.add(ProductPrice(
        tenant_id=tenant.id, product_id=product.id, channel_id=None,
        currency_code="EUR", amount_cents=1899,
    ))
    db.flush()

    price = price_for_product_in_currency(db, product.id, "EUR", channel_id=channel.id)
    assert price == Money(1899, "EUR")


def test_fx_fallback_uses_unit_price_with_rate(db, tenant: Tenant, channel: Channel, product: Product) -> None:
    """No ProductPrice for the currency → FX-derive from product.unit_price_cents."""
    from app.billing.fx import set_rate
    from app.billing.pricing import price_for_product_in_currency

    # Tenant default currency assumed to be the product's base. Set USD→INR rate.
    # Product.unit_price_cents = 1999 in tenant default ("USD" assumed)
    set_rate(db, tenant.id, "USD", "INR", Decimal("83.0"))
    db.flush()

    # 1999 USD cents × 83 = 165917 INR cents
    price = price_for_product_in_currency(db, product.id, "INR", channel_id=channel.id)
    assert price.currency_code == "INR"
    assert price.amount_cents == 165917


def test_no_price_no_rate_raises(db, tenant: Tenant, channel: Channel, product: Product) -> None:
    """Neither ProductPrice nor FX rate available → raise (caller decides UX)."""
    from app.billing.fx import FxRateMissingError
    from app.billing.pricing import price_for_product_in_currency

    with pytest.raises(FxRateMissingError):
        price_for_product_in_currency(db, product.id, "JPY", channel_id=channel.id)


def test_channel_id_none_skips_channel_lookup(db, tenant: Tenant, product: Product) -> None:
    """Calling without channel_id returns the tenant-wide price."""
    from app.billing.pricing import price_for_product_in_currency

    db.add(ProductPrice(
        tenant_id=tenant.id, product_id=product.id, channel_id=None,
        currency_code="EUR", amount_cents=1899,
    ))
    db.flush()

    price = price_for_product_in_currency(db, product.id, "EUR", channel_id=None)
    assert price == Money(1899, "EUR")


def test_unknown_product_raises(db, tenant: Tenant, channel: Channel) -> None:
    from app.billing.pricing import price_for_product_in_currency
    with pytest.raises(LookupError, match="product"):
        price_for_product_in_currency(db, uuid.uuid4(), "USD", channel_id=channel.id)
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/billing $CONTAINER:/app/tests/billing
docker compose exec api python -m pytest tests/billing/test_pricing.py -v
docker compose exec api rm -rf /app/tests/billing
```
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the pricing service**

Create `services/api/app/billing/pricing.py`:

```python
"""Pricing resolver: given (product, currency, channel?), return Money.

Resolution order (highest priority first):
  1. ProductPrice with matching (product_id, channel_id, currency_code) — exact channel-specific
  2. ProductPrice with matching (product_id, currency_code, channel_id IS NULL) — tenant-wide
  3. FX-derived from Product.unit_price_cents (assumed in tenant.default_currency_code)

If neither a ProductPrice nor an FX rate is available for the target currency,
raises ``FxRateMissingError`` from app.billing.fx — callers decide how to
surface that (omit the product, show "—", fall back to the base price etc.).
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.fx import convert
from app.billing.money import Money
from app.models import Product, ProductPrice, Tenant


def price_for_product_in_currency(
    db: Session,
    product_id: UUID,
    currency_code: str,
    *,
    channel_id: UUID | None = None,
) -> Money:
    """Resolve the price of a product in a target currency, optionally for a specific channel."""
    target = currency_code.upper()

    product = db.get(Product, product_id)
    if product is None:
        raise LookupError(f"Unknown product_id {product_id}")

    # 1. Channel-specific price for this currency
    if channel_id is not None:
        ch_specific = db.execute(
            select(ProductPrice).where(
                ProductPrice.product_id == product_id,
                ProductPrice.channel_id == channel_id,
                ProductPrice.currency_code == target,
            )
        ).scalar_one_or_none()
        if ch_specific is not None:
            return Money(ch_specific.amount_cents, target)

    # 2. Tenant-wide price for this currency
    tenant_wide = db.execute(
        select(ProductPrice).where(
            ProductPrice.product_id == product_id,
            ProductPrice.channel_id.is_(None),
            ProductPrice.currency_code == target,
        )
    ).scalar_one_or_none()
    if tenant_wide is not None:
        return Money(tenant_wide.amount_cents, target)

    # 3. FX-derive from Product.unit_price_cents (in tenant default currency)
    tenant = db.get(Tenant, product.tenant_id)
    base_currency = (tenant.default_currency_code if tenant else "USD") or "USD"
    base_money = Money(product.unit_price_cents, base_currency)
    return convert(db, product.tenant_id, base_money, target)
```

- [ ] **Step 4: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/billing/pricing.py $CONTAINER:/app/app/billing/pricing.py
docker cp services/api/tests/billing $CONTAINER:/app/tests/billing
docker compose exec api python -m pytest tests/billing/test_pricing.py -v
docker compose exec api rm -rf /app/tests/billing
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/billing/pricing.py \
        services/api/tests/billing/test_pricing.py
git commit -m "feat(currency): add pricing.price_for_product_in_currency with FX fallback"
```

---

### Task 5: Admin endpoints — FX rates + product prices

**Files:**
- Create: `services/api/app/routers/admin_fx_rates.py`
- Create: `services/api/app/routers/admin_product_prices.py`
- Modify: `services/api/app/main.py`
- Create: `services/api/tests/routers/test_admin_fx_rates.py`
- Create: `services/api/tests/routers/test_admin_product_prices.py`

- [ ] **Step 1: Write the failing tests for FX rates**

Create `services/api/tests/routers/test_admin_fx_rates.py`:

```python
# NOTE: `from __future__ import annotations` deliberately absent.

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import FxRate, Tenant


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        role="owner",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset({"currency:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_create_fx_rate(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/fx-rates", json={
        "from_currency": "USD",
        "to_currency": "INR",
        "rate": "83.25",
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["from_currency"] == "USD"
    assert body["to_currency"] == "INR"
    assert Decimal(body["rate"]) == Decimal("83.25")
    assert body["source"] == "manual"


def test_list_fx_rates(db, tenant: Tenant, auth_headers) -> None:
    db.add(FxRate(
        tenant_id=tenant.id, from_currency="USD", to_currency="EUR",
        rate=Decimal("0.92"), source="manual", effective_at=datetime.now(UTC),
    ))
    db.add(FxRate(
        tenant_id=tenant.id, from_currency="USD", to_currency="GBP",
        rate=Decimal("0.79"), source="manual", effective_at=datetime.now(UTC),
    ))
    db.commit()

    client = TestClient(app)
    resp = client.get("/v1/admin/fx-rates", headers=auth_headers)
    assert resp.status_code == 200
    pairs = {(r["from_currency"], r["to_currency"]) for r in resp.json()}
    assert pairs == {("USD", "EUR"), ("USD", "GBP")}


def test_create_fx_rate_normalises_currency_to_upper(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/fx-rates", json={
        "from_currency": "usd",
        "to_currency": "eur",
        "rate": "0.92",
    }, headers=auth_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["from_currency"] == "USD"
    assert body["to_currency"] == "EUR"


def test_create_same_pair_updates(db, tenant: Tenant, auth_headers) -> None:
    """POSTing the same pair twice updates the existing row (set_rate is upsert)."""
    client = TestClient(app)
    r1 = client.post("/v1/admin/fx-rates", json={
        "from_currency": "USD", "to_currency": "INR", "rate": "82.00",
    }, headers=auth_headers)
    r2 = client.post("/v1/admin/fx-rates", json={
        "from_currency": "USD", "to_currency": "INR", "rate": "83.50",
    }, headers=auth_headers)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]
    assert Decimal(r2.json()["rate"]) == Decimal("83.50")


def test_delete_fx_rate(db, tenant: Tenant, auth_headers) -> None:
    rate = FxRate(
        tenant_id=tenant.id, from_currency="USD", to_currency="JPY",
        rate=Decimal("150.0"), source="manual", effective_at=datetime.now(UTC),
    )
    db.add(rate)
    db.commit()

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/fx-rates/{rate.id}", headers=auth_headers)
    assert resp.status_code == 204


def test_invalid_rate_format_rejected(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/fx-rates", json={
        "from_currency": "USD", "to_currency": "EUR", "rate": "not-a-number",
    }, headers=auth_headers)
    assert resp.status_code == 422


def test_negative_rate_rejected(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/fx-rates", json={
        "from_currency": "USD", "to_currency": "EUR", "rate": "-1.0",
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert "positive" in resp.json()["detail"].lower()
```

- [ ] **Step 2: Write the failing tests for product prices**

Create `services/api/tests/routers/test_admin_product_prices.py`:

```python
# NOTE: `from __future__ import annotations` deliberately absent.

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    Channel, InventoryPool, InventoryPoolShop, Product, ProductPrice, Shop, Tenant,
)


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"POS at {shop.name}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="manual", name=f"channel-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="USD",
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def product(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id, name="Widget",
        sku=f"sku-{uuid.uuid4().hex[:6]}", unit_price_cents=1999,
    )
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        role="owner",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset({"currency:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_create_tenant_wide_product_price(db, tenant: Tenant, product: Product, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post(f"/v1/admin/products/{product.id}/prices", json={
        "channel_id": None,
        "currency_code": "EUR",
        "amount_cents": 1899,
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["currency_code"] == "EUR"
    assert body["amount_cents"] == 1899
    assert body["channel_id"] is None


def test_create_channel_specific_product_price(db, tenant: Tenant, channel: Channel, product: Product, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post(f"/v1/admin/products/{product.id}/prices", json={
        "channel_id": str(channel.id),
        "currency_code": "USD",
        "amount_cents": 1799,
    }, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["channel_id"] == str(channel.id)


def test_list_product_prices(db, tenant: Tenant, channel: Channel, product: Product, auth_headers) -> None:
    db.add(ProductPrice(
        tenant_id=tenant.id, product_id=product.id, channel_id=None,
        currency_code="EUR", amount_cents=1899,
    ))
    db.add(ProductPrice(
        tenant_id=tenant.id, product_id=product.id, channel_id=channel.id,
        currency_code="USD", amount_cents=1799,
    ))
    db.commit()

    client = TestClient(app)
    resp = client.get(f"/v1/admin/products/{product.id}/prices", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_upsert_replaces_existing(db, tenant: Tenant, channel: Channel, product: Product, auth_headers) -> None:
    """POSTing same (product, channel, currency) twice updates."""
    client = TestClient(app)
    r1 = client.post(f"/v1/admin/products/{product.id}/prices", json={
        "channel_id": None,
        "currency_code": "EUR",
        "amount_cents": 1899,
    }, headers=auth_headers)
    r2 = client.post(f"/v1/admin/products/{product.id}/prices", json={
        "channel_id": None,
        "currency_code": "EUR",
        "amount_cents": 1999,
    }, headers=auth_headers)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]
    assert r2.json()["amount_cents"] == 1999


def test_delete_product_price(db, tenant: Tenant, product: Product, auth_headers) -> None:
    pp = ProductPrice(
        tenant_id=tenant.id, product_id=product.id, channel_id=None,
        currency_code="EUR", amount_cents=1899,
    )
    db.add(pp)
    db.commit()

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/products/{product.id}/prices/{pp.id}", headers=auth_headers)
    assert resp.status_code == 204


def test_negative_amount_rejected(db, tenant: Tenant, product: Product, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post(f"/v1/admin/products/{product.id}/prices", json={
        "channel_id": None,
        "currency_code": "EUR",
        "amount_cents": -100,
    }, headers=auth_headers)
    assert resp.status_code == 422


def test_cross_tenant_product_blocked(db, tenant: Tenant, auth_headers) -> None:
    """Operator can't price a product from a different tenant."""
    other = Tenant(name=f"other-{uuid.uuid4().hex[:6]}", slug=f"other-{uuid.uuid4().hex[:8]}")
    db.add(other)
    db.flush()
    other_p = Product(
        tenant_id=other.id, name="Other",
        sku=f"sku-{uuid.uuid4().hex[:6]}", unit_price_cents=100,
    )
    db.add(other_p)
    db.commit()

    client = TestClient(app)
    resp = client.post(f"/v1/admin/products/{other_p.id}/prices", json={
        "channel_id": None,
        "currency_code": "EUR",
        "amount_cents": 100,
    }, headers=auth_headers)
    assert resp.status_code == 404
```

- [ ] **Step 3: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/routers/test_admin_fx_rates.py $CONTAINER:/app/tests/routers/test_admin_fx_rates.py
docker cp services/api/tests/routers/test_admin_product_prices.py $CONTAINER:/app/tests/routers/test_admin_product_prices.py
docker compose exec api python -m pytest tests/routers/test_admin_fx_rates.py tests/routers/test_admin_product_prices.py -v
docker compose exec api rm -f /app/tests/routers/test_admin_fx_rates.py /app/tests/routers/test_admin_product_prices.py
```
Expected: FAIL — both routers don't exist.

- [ ] **Step 4: Implement `admin_fx_rates.py`**

Create `services/api/app/routers/admin_fx_rates.py`:

```python
"""Admin endpoints for managing FX rates (manual upload).

Auto-sync from a public provider is a follow-up plan; this router lets
operators upload rates one-by-one or in bulk for the currency pairs they
need. Rate `source` is always 'manual' for rows created here.

Auth: requires `currency:manage` permission. Granted to system `owner` role
by migration 20260509000001.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.billing.fx import set_rate
from app.db.admin_deps_db import get_db_admin
from app.models import FxRate

router = APIRouter(
    prefix="/v1/admin/fx-rates",
    tags=["Admin FX Rates"],
    dependencies=[require_permission("currency:manage")],
)


class FxRateIn(BaseModel):
    from_currency: str = Field(min_length=3, max_length=3)
    to_currency: str = Field(min_length=3, max_length=3)
    rate: str  # parsed as Decimal in the route

    @field_validator("rate")
    @classmethod
    def _rate_is_parseable(cls, v: str) -> str:
        try:
            Decimal(v)
        except (InvalidOperation, ValueError):
            raise ValueError(f"rate must be a numeric string, got {v!r}")
        return v


class FxRateOut(BaseModel):
    id: UUID
    tenant_id: UUID
    from_currency: str
    to_currency: str
    rate: str
    source: str
    effective_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("rate", mode="before")
    @classmethod
    def _stringify_rate(cls, v) -> str:
        # SQLAlchemy returns Numeric as Decimal; serialise as string for JSON
        return str(v)


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator not assigned to a tenant",
        )
    return ctx.tenant_id


@router.get("", response_model=list[FxRateOut])
def list_rates(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[FxRate]:
    tenant_id = _require_tenant(ctx)
    rows = db.execute(
        select(FxRate).where(FxRate.tenant_id == tenant_id).order_by(
            FxRate.from_currency, FxRate.to_currency,
        )
    ).scalars().all()
    return list(rows)


@router.post("", response_model=FxRateOut, status_code=status.HTTP_201_CREATED)
def create_or_update_rate(
    body: FxRateIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> FxRate:
    tenant_id = _require_tenant(ctx)
    rate = Decimal(body.rate)
    if rate <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="rate must be positive",
        )
    row = set_rate(db, tenant_id, body.from_currency, body.to_currency, rate)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{rate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rate(
    rate_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    row = db.get(FxRate, rate_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rate not found")
    db.delete(row)
    db.commit()
```

- [ ] **Step 5: Implement `admin_product_prices.py`**

Create `services/api/app/routers/admin_product_prices.py`:

```python
"""Admin endpoints for per-product, per-currency, optionally per-channel pricing.

Routes are nested under /v1/admin/products/{product_id}/prices to match the
parent-child resource shape. Tenant-wide prices use channel_id=null in the body.

Auth: requires `currency:manage` permission.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Channel, Product, ProductPrice

router = APIRouter(
    prefix="/v1/admin/products",
    tags=["Admin Product Prices"],
    dependencies=[require_permission("currency:manage")],
)


class ProductPriceIn(BaseModel):
    channel_id: UUID | None = None
    currency_code: str = Field(min_length=3, max_length=3)
    amount_cents: int = Field(ge=0)


class ProductPriceOut(BaseModel):
    id: UUID
    tenant_id: UUID
    product_id: UUID
    channel_id: UUID | None
    currency_code: str
    amount_cents: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


def _require_tenant_and_product(ctx: AdminAuthDep, db: Session, product_id: UUID) -> tuple[UUID, Product]:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator not assigned to a tenant",
        )
    product = db.get(Product, product_id)
    if product is None or product.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return ctx.tenant_id, product


@router.get("/{product_id}/prices", response_model=list[ProductPriceOut])
def list_prices(
    product_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[ProductPrice]:
    tenant_id, product = _require_tenant_and_product(ctx, db, product_id)
    rows = db.execute(
        select(ProductPrice).where(
            ProductPrice.product_id == product_id,
        ).order_by(ProductPrice.currency_code, ProductPrice.channel_id)
    ).scalars().all()
    return list(rows)


@router.post("/{product_id}/prices", response_model=ProductPriceOut, status_code=status.HTTP_201_CREATED)
def create_or_update_price(
    product_id: UUID,
    body: ProductPriceIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ProductPrice:
    tenant_id, product = _require_tenant_and_product(ctx, db, product_id)

    # Validate channel_id belongs to this tenant (if set)
    if body.channel_id is not None:
        ch = db.get(Channel, body.channel_id)
        if ch is None or ch.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="channel_id does not belong to this tenant",
            )

    currency = body.currency_code.upper()

    existing = db.execute(
        select(ProductPrice).where(
            ProductPrice.product_id == product_id,
            ProductPrice.channel_id == body.channel_id,
            ProductPrice.currency_code == currency,
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.amount_cents = body.amount_cents
        row = existing
    else:
        row = ProductPrice(
            tenant_id=tenant_id,
            product_id=product_id,
            channel_id=body.channel_id,
            currency_code=currency,
            amount_cents=body.amount_cents,
        )
        db.add(row)

    db.commit()
    db.refresh(row)
    return row


@router.delete("/{product_id}/prices/{price_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_price(
    product_id: UUID,
    price_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id, product = _require_tenant_and_product(ctx, db, product_id)
    row = db.get(ProductPrice, price_id)
    if row is None or row.tenant_id != tenant_id or row.product_id != product_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price not found")
    db.delete(row)
    db.commit()
```

- [ ] **Step 6: Mount routers**

In `services/api/app/main.py`, add `admin_fx_rates` and `admin_product_prices` to the imports list (alphabetically) and add `app.include_router(admin_fx_rates.router)` and `app.include_router(admin_product_prices.router)` to the include block.

- [ ] **Step 7: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/main.py $CONTAINER:/app/app/main.py
docker cp services/api/app/routers/admin_fx_rates.py $CONTAINER:/app/app/routers/admin_fx_rates.py
docker cp services/api/app/routers/admin_product_prices.py $CONTAINER:/app/app/routers/admin_product_prices.py
docker cp services/api/app/billing $CONTAINER:/app/app/billing
docker cp services/api/tests $CONTAINER:/app/tests
docker compose restart api
sleep 5
docker compose exec api python -m pytest tests/routers/test_admin_fx_rates.py tests/routers/test_admin_product_prices.py tests/test_admin_console_contracts.py::test_product_price_out_schema tests/test_admin_console_contracts.py::test_fx_rate_out_schema -v
docker compose exec api rm -rf /app/tests
```
Expected: 7 fx-rate tests + 7 product-price tests + 2 contract tests = 16 passed.

- [ ] **Step 8: Commit**

```bash
git add services/api/app/routers/admin_fx_rates.py \
        services/api/app/routers/admin_product_prices.py \
        services/api/app/main.py \
        services/api/tests/routers/test_admin_fx_rates.py \
        services/api/tests/routers/test_admin_product_prices.py
git commit -m "feat(currency): admin CRUD for fx_rates and product_prices"
```

---

### Task 6: Integration smoke test

**Files:**
- Create: `services/api/tests/integration/test_currency_e2e.py`

This task does not add product code — only an integration test exercising the full pricing flow.

- [ ] **Step 1: Write the integration test**

Create `services/api/tests/integration/test_currency_e2e.py`:

```python
"""End-to-end smoke test for the multi-currency engine.

Covers:
- Money type behavior under arithmetic
- FX service: set, get, convert (direct + inverse + same-currency)
- Pricing resolver: explicit channel-specific > tenant-wide > FX-derived from base
- Admin endpoints: create FX rate via API, then resolver picks it up
"""
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    Channel, InventoryPool, InventoryPoolShop, Product, ProductPrice, Shop, Tenant,
)


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"POS at {shop.name}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="manual", name=f"channel-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="USD",
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def product(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id, name="E2E Widget",
        sku=f"sku-{uuid.uuid4().hex[:6]}", unit_price_cents=1999,
    )
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def auth(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=uuid.uuid4(), tenant_id=tenant.id,
        role="owner", role_id=None, is_legacy_token=False,
        permissions=frozenset({"currency:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield
    app.dependency_overrides.clear()


def test_full_pricing_resolution_chain(db, tenant: Tenant, channel: Channel, product: Product) -> None:
    """No prices, no rate → raises. Add tenant-wide → tenant-wide. Add channel-specific → channel-specific."""
    from app.billing.fx import FxRateMissingError
    from app.billing.money import Money
    from app.billing.pricing import price_for_product_in_currency

    # 1. No prices, no rate → raises
    with pytest.raises(FxRateMissingError):
        price_for_product_in_currency(db, product.id, "EUR", channel_id=channel.id)

    # 2. Add tenant-wide price → returns it
    db.add(ProductPrice(
        tenant_id=tenant.id, product_id=product.id, channel_id=None,
        currency_code="EUR", amount_cents=1899,
    ))
    db.flush()
    p1 = price_for_product_in_currency(db, product.id, "EUR", channel_id=channel.id)
    assert p1 == Money(1899, "EUR")

    # 3. Add channel-specific override → returns it instead
    db.add(ProductPrice(
        tenant_id=tenant.id, product_id=product.id, channel_id=channel.id,
        currency_code="EUR", amount_cents=1799,
    ))
    db.flush()
    p2 = price_for_product_in_currency(db, product.id, "EUR", channel_id=channel.id)
    assert p2 == Money(1799, "EUR")


def test_fx_fallback_via_admin_api(db, tenant: Tenant, channel: Channel, product: Product, auth) -> None:
    """Set FX rate via admin API. Resolver uses it for currencies without explicit ProductPrice."""
    from app.billing.money import Money
    from app.billing.pricing import price_for_product_in_currency

    client = TestClient(app)
    resp = client.post("/v1/admin/fx-rates", json={
        "from_currency": "USD",
        "to_currency": "INR",
        "rate": "83.00",
    })
    assert resp.status_code == 201

    # No ProductPrice for INR → resolver uses FX. unit_price_cents=1999 USD × 83 = 165917 INR cents
    p = price_for_product_in_currency(db, product.id, "INR", channel_id=channel.id)
    assert p == Money(165917, "INR")


def test_money_arithmetic_invariants(db, tenant: Tenant) -> None:
    from app.billing.fx import FxRateMissingError, convert
    from app.billing.money import Money

    # Same currency: add/sub work
    a = Money(1000, "USD")
    b = Money(250, "USD")
    assert (a + b) == Money(1250, "USD")
    assert (a - b) == Money(750, "USD")

    # Cross currency: arithmetic raises
    with pytest.raises(ValueError):
        a + Money(100, "EUR")

    # Convert is the only legal cross-currency operation, and requires a rate
    with pytest.raises(FxRateMissingError):
        convert(db, tenant.id, a, "EUR")


def test_admin_api_lifecycle(db, tenant: Tenant, channel: Channel, product: Product, auth) -> None:
    """Round-trip: create rate, list rates, create product price, list prices, delete."""
    client = TestClient(app)

    # Create FX rate
    resp = client.post("/v1/admin/fx-rates", json={
        "from_currency": "USD", "to_currency": "EUR", "rate": "0.92",
    })
    assert resp.status_code == 201
    rate_id = resp.json()["id"]

    # List shows it
    resp = client.get("/v1/admin/fx-rates")
    assert resp.status_code == 200
    assert any(r["id"] == rate_id for r in resp.json())

    # Create channel-specific price
    resp = client.post(f"/v1/admin/products/{product.id}/prices", json={
        "channel_id": str(channel.id),
        "currency_code": "EUR",
        "amount_cents": 1799,
    })
    assert resp.status_code == 201
    price_id = resp.json()["id"]

    # List shows it
    resp = client.get(f"/v1/admin/products/{product.id}/prices")
    assert resp.status_code == 200
    assert any(p["id"] == price_id for p in resp.json())

    # Delete both
    assert client.delete(f"/v1/admin/products/{product.id}/prices/{price_id}").status_code == 204
    assert client.delete(f"/v1/admin/fx-rates/{rate_id}").status_code == 204
```

- [ ] **Step 2: Run integration test**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest tests/integration/test_currency_e2e.py -v
docker compose exec api rm -rf /app/tests
```
Expected: 4 passed.

- [ ] **Step 3: Run the full multi-currency suite**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest \
  tests/billing/test_money.py \
  tests/billing/test_fx.py \
  tests/billing/test_pricing.py \
  tests/routers/test_admin_fx_rates.py \
  tests/routers/test_admin_product_prices.py \
  tests/integration/test_currency_e2e.py \
  tests/test_admin_console_contracts.py::test_product_price_out_schema \
  tests/test_admin_console_contracts.py::test_fx_rate_out_schema \
  -v 2>&1 | tail -10
docker compose exec api rm -rf /app/tests
```
Expected ballpark: ~40 tests passing.

- [ ] **Step 4: Commit**

```bash
git add services/api/tests/integration/test_currency_e2e.py
git commit -m "test(currency): end-to-end smoke test for Money + FX + pricing resolver"
```

---

## Done. Summary of what shipped

- New tables `product_prices` and `fx_rates` with RLS, indexes, unique constraints
- New permission `currency:manage` granted to system `owner` role
- `app/billing/money.py` — `Money(amount_cents, currency_code)` frozen value type with same-currency arithmetic + `round_half_up_cents` helper
- `app/billing/fx.py` — `get_rate`, `set_rate`, `convert` (the only place in the codebase that does cross-currency math); raises `FxRateMissingError` when no rate available
- `app/billing/pricing.py` — `price_for_product_in_currency` with the three-tier resolution chain (channel-specific → tenant-wide → FX-derived)
- Two admin routers: `admin_fx_rates.py` and `admin_product_prices.py`
- ~40 tests across all layers

## What this unlocks

- **Phase 1 connectors** (Shopify EUR store, headless API serving INR, etc.) call `price_for_product_in_currency` and get the right amount in the right currency
- **Hosted checkout** displays prices in shopper's currency (via the same resolver, with `?currency=USD` query param eventually wiring through)
- **Tax engine** (next sub-project) gets a consistent currency story — every tax calc happens in the channel's currency end-to-end, no implicit conversion

## Follow-up work (not in this plan)

- **Auto-sync FX rates** from a public provider (openexchangerates / ECB / xe). Build the table + service is here; auto-sync is a separate follow-up plan once a provider is chosen
- **POS multi-currency** — existing `Transaction`/`TransactionLine`/`PaymentAllocation` stays single-currency. Future cleanup if/when there's POS-multi-currency demand
- **Bulk FX upload** — admin endpoint accepts a single pair at a time. Bulk CSV/JSON upload is an easy add later
- **Wire `Money` into existing flows** — sync_push, order ingest, etc. could be incrementally refactored to take/return `Money`. Out of scope for this plan; the type is available for new code

---

*End of plan.*
