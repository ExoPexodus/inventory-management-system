# Plan Entitlements + Engineering Flags Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local entitlement-resolution layer that gates IMS API features by plan, plus a separate engineering rollout flag system for gradual launches. The two layer at every call site: entitlement check first (commercial), engineering flag second (rollout).

**Architecture:** The IMS keeps its existing `TenantLicenseCache` + `LicenseContext` (which already exposes `plan_codename`, `active_addons`, `max_shops`, etc.). On top of that, this plan adds a new `app/billing/` module containing: a feature catalog as config-as-code (`features.py`), a plan-codename → feature-value mapping as config-as-code (`plans.py`), a resolver service that merges defaults + plan + DB-stored per-tenant overrides (`entitlements.py`), and an engineering-flag resolver (`flags.py`). Two new tables (`tenant_feature_overrides`, `feature_flags`) and one new permission (`entitlements:manage`) ship in a single migration. A FastAPI dependency exposes a typed `Entitlements` API to route handlers; admin CRUD endpoints let IMS staff manage overrides and flags. Redis caches resolved values with invalidation on writes. The resolver's `_load_plan_features()` is the single seam to swap when platform-side feature management ships later.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, PostgreSQL, Redis (existing — `redis_conn()` from `app/worker/queue.py`), pytest

**Out of scope (deferred):**
- Platform-service-side admin UI for editing plan-feature mappings (separate plan; required before going live with feature gates whose commercial accuracy needs editing without code deploys — see memory `platform-side-entitlement-followup.md`)
- Admin-web UI for managing overrides/flags (this plan ships only the backend endpoints; admin-web work is a follow-up frontend task)

---

### Task 1: Migration + SQLAlchemy models + contract tests

**Files:**
- Create: `services/api/alembic/versions/20260506000001_entitlement_overrides_and_flags.py`
- Modify: `services/api/app/models/tables.py`
- Modify: `services/api/app/models/__init__.py`
- Modify: `services/api/tests/test_admin_console_contracts.py`

- [ ] **Step 1: Write failing contract tests for the new Pydantic schemas**

Add to `services/api/tests/test_admin_console_contracts.py`:

```python
def test_tenant_feature_override_out_schema() -> None:
    from app.routers.admin_entitlements import TenantFeatureOverrideOut

    o = TenantFeatureOverrideOut(
        id=uuid4(),
        tenant_id=uuid4(),
        feature_key="headless_api",
        value=True,
        reason="Beta access for design partner",
        expires_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    d = o.model_dump(mode="json")
    assert d["feature_key"] == "headless_api"
    assert d["value"] is True
    assert d["reason"] == "Beta access for design partner"


def test_feature_flag_out_schema() -> None:
    from app.routers.admin_entitlements import FeatureFlagOut

    f = FeatureFlagOut(
        id=uuid4(),
        key="stock_reservations_enabled",
        default_state=False,
        rollout_rules={"percent": 25, "allowlist": []},
        description="Soft TTL stock reservation engine",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    d = f.model_dump(mode="json")
    assert d["key"] == "stock_reservations_enabled"
    assert d["default_state"] is False
    assert d["rollout_rules"]["percent"] == 25
```

If the imports `from datetime import UTC, datetime` and `from uuid import uuid4` are not already at the top of the test file, add them.

- [ ] **Step 2: Run tests to confirm they fail**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp /home/devadmin/inventory-management-system/services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest tests/test_admin_console_contracts.py::test_tenant_feature_override_out_schema tests/test_admin_console_contracts.py::test_feature_flag_out_schema -v
docker compose exec api rm -rf /app/tests
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routers.admin_entitlements'`

- [ ] **Step 3: Add SQLAlchemy models**

In `services/api/app/models/tables.py`, add at the end of the file (after `TenantLicenseCache`):

```python
class TenantFeatureOverride(Base):
    __tablename__ = "tenant_feature_overrides"
    __table_args__ = (
        UniqueConstraint("tenant_id", "feature_key", name="uq_tenant_feature_override_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    feature_key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class FeatureFlag(Base):
    __tablename__ = "feature_flags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    default_state: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rollout_rules: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

The `value` column on `TenantFeatureOverride` is JSONB so it can hold any feature value type (bool, int, string). The resolver coerces.

- [ ] **Step 4: Export the new models**

In `services/api/app/models/__init__.py`, add `FeatureFlag` and `TenantFeatureOverride` to the import list and `__all__`. The list is alphabetized; insert in order:

```python
# in the import block, after Device:
    FeatureFlag,
# after Supplier:
    TenantFeatureOverride,
```

And the same in `__all__`.

- [ ] **Step 5: Write the Alembic migration**

Create `services/api/alembic/versions/20260506000001_entitlement_overrides_and_flags.py`:

```python
"""Add tenant_feature_overrides + feature_flags tables; seed entitlements:manage permission

Revision ID: 20260506000001
Revises: 20260503000001
Create Date: 2026-05-06 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

revision = "20260506000001"
down_revision = "20260503000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. tenant_feature_overrides
    op.create_table(
        "tenant_feature_overrides",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feature_key", sa.String(128), nullable=False),
        sa.Column("value", JSONB, nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "feature_key", name="uq_tenant_feature_override_key"),
    )
    op.create_index(
        "ix_tenant_feature_overrides_tenant_id",
        "tenant_feature_overrides",
        ["tenant_id"],
    )

    # 2. feature_flags
    op.create_table(
        "feature_flags",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(128), unique=True, nullable=False),
        sa.Column("default_state", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("rollout_rules", JSONB, nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 3. Seed permission. Deliberately NOT auto-granted to any role: this is an
    #    IMS-staff-only permission (overrides bypass commercial gates) and must
    #    be granted to specific operators by a staff workflow, not by default.
    conn = op.get_bind()
    conn.execute(sa.text(
        "INSERT INTO permissions (id, codename, description) "
        "VALUES (gen_random_uuid(), 'entitlements:manage', "
        "'Manage tenant feature overrides and engineering flags (IMS staff only)') "
        "ON CONFLICT (codename) DO UPDATE SET description = EXCLUDED.description"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "DELETE FROM role_permissions WHERE permission_id IN "
        "(SELECT id FROM permissions WHERE codename = 'entitlements:manage')"
    ))
    conn.execute(sa.text("DELETE FROM permissions WHERE codename = 'entitlements:manage'"))
    op.drop_table("feature_flags")
    op.drop_index("ix_tenant_feature_overrides_tenant_id", table_name="tenant_feature_overrides")
    op.drop_table("tenant_feature_overrides")
```

- [ ] **Step 6: Run migration in the running container**

```bash
docker compose exec api alembic upgrade head
```
Expected: `Running upgrade 20260503000001 -> 20260506000001, Add tenant_feature_overrides + feature_flags tables; seed entitlements:manage permission`

- [ ] **Step 7: Verify tables and permission exist**

```bash
docker compose exec db psql -U postgres -d ims -c "\d tenant_feature_overrides"
docker compose exec db psql -U postgres -d ims -c "\d feature_flags"
docker compose exec db psql -U postgres -d ims -c "SELECT codename FROM permissions WHERE codename = 'entitlements:manage'"
```
Expected: both table descriptions printed; the permission row returned.

- [ ] **Step 8: Commit**

```bash
git add services/api/alembic/versions/20260506000001_entitlement_overrides_and_flags.py \
        services/api/app/models/tables.py \
        services/api/app/models/__init__.py \
        services/api/tests/test_admin_console_contracts.py
git commit -m "feat(billing): add tenant_feature_overrides + feature_flags tables"
```

(The contract tests still fail because `app.routers.admin_entitlements` does not exist yet — that's Task 7. They stay red until then; this is intentional TDD.)

---

### Task 2: Feature catalog + plan-feature mapping (config-as-code)

**Files:**
- Create: `services/api/app/billing/__init__.py`
- Create: `services/api/app/billing/features.py`
- Create: `services/api/app/billing/plans.py`
- Create: `services/api/tests/billing/__init__.py`
- Create: `services/api/tests/billing/test_features_catalog.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/billing/__init__.py` as an empty file, then create `services/api/tests/billing/test_features_catalog.py`:

```python
from __future__ import annotations

import pytest


def test_feature_catalog_keys_unique() -> None:
    from app.billing.features import FEATURE_CATALOG
    keys = [f.key for f in FEATURE_CATALOG]
    assert len(keys) == len(set(keys)), "Duplicate keys in FEATURE_CATALOG"


def test_feature_catalog_has_known_features() -> None:
    from app.billing.features import FEATURE_CATALOG
    keys = {f.key for f in FEATURE_CATALOG}
    # These are the bare-minimum entries the e-commerce pivot relies on.
    expected = {
        "max_channels",
        "shopify_connector",
        "woocommerce_connector",
        "headless_api",
        "hosted_checkout",
        "max_products",
    }
    missing = expected - keys
    assert not missing, f"Catalog missing expected feature keys: {missing}"


def test_feature_value_types_are_supported() -> None:
    from app.billing.features import FEATURE_CATALOG, ValueType
    for f in FEATURE_CATALOG:
        assert f.value_type in {ValueType.BOOL, ValueType.NUMERIC, ValueType.ENUM}, \
            f"Unsupported value_type on {f.key}: {f.value_type}"


def test_plan_map_lookup_falls_back_to_default() -> None:
    from app.billing.features import resolve_default
    from app.billing.plans import resolve_plan_value

    # An unknown plan codename should still resolve via the catalog default.
    val = resolve_plan_value("plan-that-does-not-exist", "headless_api")
    assert val == resolve_default("headless_api")


def test_plan_map_pro_plan_includes_headless_api() -> None:
    from app.billing.plans import resolve_plan_value
    assert resolve_plan_value("pro", "headless_api") is True


def test_plan_map_free_plan_does_not_include_headless_api() -> None:
    from app.billing.plans import resolve_plan_value
    assert resolve_plan_value("free", "headless_api") is False
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp /home/devadmin/inventory-management-system/services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest tests/billing/test_features_catalog.py -v
docker compose exec api rm -rf /app/tests
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.billing'`

- [ ] **Step 3: Create the billing package init**

Create `services/api/app/billing/__init__.py` as an empty file (it's a package marker; submodules import explicitly).

- [ ] **Step 4: Write the feature catalog**

Create `services/api/app/billing/features.py`:

```python
"""Feature catalog — config-as-code source of truth for what features exist.

This file declares every feature key that any part of the IMS may gate behind a plan
or override. Adding a new feature gate begins by adding an entry here; without an
entry, the resolver returns the type's "off" default and may log a warning.

Plan-codename -> value mapping lives in plans.py. Per-tenant overrides live in
the tenant_feature_overrides table. The resolver in entitlements.py merges the
three sources: tenant override > plan value > catalog default.

When platform-side plan management ships, the seam to swap is plans.py (single
file). This file stays untouched.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ValueType(str, Enum):
    BOOL = "bool"
    NUMERIC = "numeric"  # integer limit (e.g. max_channels)
    ENUM = "enum"        # one-of string (reserved for future)


@dataclass(frozen=True)
class FeatureDefinition:
    key: str
    value_type: ValueType
    default: Any
    description: str


# Canonical catalog. Order is irrelevant; the resolver looks up by key.
FEATURE_CATALOG: list[FeatureDefinition] = [
    # --- Channel + integration features (pivot Phase 1) ---
    FeatureDefinition(
        key="max_channels",
        value_type=ValueType.NUMERIC,
        default=1,
        description="Maximum number of sales channels (Shopify/Woo/headless/POS) per tenant",
    ),
    FeatureDefinition(
        key="shopify_connector",
        value_type=ValueType.BOOL,
        default=False,
        description="Allow connecting Shopify stores",
    ),
    FeatureDefinition(
        key="woocommerce_connector",
        value_type=ValueType.BOOL,
        default=False,
        description="Allow connecting WooCommerce stores",
    ),
    FeatureDefinition(
        key="headless_api",
        value_type=ValueType.BOOL,
        default=False,
        description="Allow custom storefronts to consume the public storefront REST/GraphQL API",
    ),
    FeatureDefinition(
        key="hosted_checkout",
        value_type=ValueType.BOOL,
        default=False,
        description="Allow IMS-hosted checkout for custom storefronts",
    ),
    FeatureDefinition(
        key="byo_stripe",
        value_type=ValueType.BOOL,
        default=False,
        description="Allow connecting a merchant's own Stripe account",
    ),
    FeatureDefinition(
        key="byo_razorpay",
        value_type=ValueType.BOOL,
        default=False,
        description="Allow connecting a merchant's own Razorpay account",
    ),
    FeatureDefinition(
        key="byo_paypal",
        value_type=ValueType.BOOL,
        default=False,
        description="Allow connecting a merchant's own PayPal account",
    ),
    # --- Catalog + commerce primitives (pivot Phase 0) ---
    FeatureDefinition(
        key="max_products",
        value_type=ValueType.NUMERIC,
        default=100,
        description="Maximum products in catalog",
    ),
    FeatureDefinition(
        key="multi_currency_advanced",
        value_type=ValueType.BOOL,
        default=False,
        description="Per-listing currency overrides + shopper-facing currency switching",
    ),
    FeatureDefinition(
        key="ai_product_generation",
        value_type=ValueType.BOOL,
        default=False,
        description="Generate product descriptions/images with AI",
    ),
    FeatureDefinition(
        key="email_volume_per_month",
        value_type=ValueType.NUMERIC,
        default=500,
        description="Transactional emails per month before throttling",
    ),
]


_BY_KEY: dict[str, FeatureDefinition] = {f.key: f for f in FEATURE_CATALOG}


def get_definition(key: str) -> FeatureDefinition | None:
    return _BY_KEY.get(key)


def resolve_default(key: str) -> Any:
    """Return the catalog default for a feature key, or None if unknown."""
    f = _BY_KEY.get(key)
    return f.default if f else None
```

- [ ] **Step 5: Write the plan-feature mapping**

Create `services/api/app/billing/plans.py`:

```python
"""Plan-codename -> feature-value mapping (config-as-code).

This is the LOCAL source of truth for "what does the 'pro' plan include?" until
the platform service grows a UI for editing this. Then the body of
``resolve_plan_value`` becomes the single seam to swap to a platform-synced
source (read from TenantLicenseCache.raw_payload's plan_features sub-object).

Codenames must match what the platform service emits in
TenantLicenseCache.plan_codename. See license_service.py.
"""
from __future__ import annotations

from typing import Any

from app.billing.features import resolve_default


# Per-plan overrides of catalog defaults. Anything not listed here falls back
# to FEATURE_CATALOG's default. Use the smallest possible set to keep
# review surface low; a missing entry means "use the default".
PLAN_FEATURES: dict[str, dict[str, Any]] = {
    # Trial = Pro for evaluation purposes
    "trial": {
        "max_channels": 5,
        "shopify_connector": True,
        "woocommerce_connector": True,
        "headless_api": True,
        "hosted_checkout": True,
        "byo_stripe": True,
        "byo_razorpay": True,
        "byo_paypal": True,
        "max_products": 1000,
        "multi_currency_advanced": True,
        "ai_product_generation": True,
        "email_volume_per_month": 5000,
    },
    "free": {
        "max_channels": 1,
        # everything else uses defaults (most flags off)
    },
    "starter": {
        "max_channels": 2,
        "shopify_connector": True,
        "woocommerce_connector": True,
        "max_products": 500,
        "byo_stripe": True,
        "email_volume_per_month": 1000,
    },
    "pro": {
        "max_channels": 5,
        "shopify_connector": True,
        "woocommerce_connector": True,
        "headless_api": True,
        "hosted_checkout": True,
        "byo_stripe": True,
        "byo_razorpay": True,
        "byo_paypal": True,
        "max_products": 5000,
        "multi_currency_advanced": True,
        "email_volume_per_month": 10000,
    },
    "business": {
        "max_channels": 20,
        "shopify_connector": True,
        "woocommerce_connector": True,
        "headless_api": True,
        "hosted_checkout": True,
        "byo_stripe": True,
        "byo_razorpay": True,
        "byo_paypal": True,
        "max_products": 50000,
        "multi_currency_advanced": True,
        "ai_product_generation": True,
        "email_volume_per_month": 100000,
    },
    # Legacy / unknown plans behave as catalog defaults (= mostly off, very limited)
}


def resolve_plan_value(plan_codename: str, feature_key: str) -> Any:
    """Resolve a feature value for a plan codename, falling back to the catalog default.

    This function is the single seam to replace when platform-side plan-feature
    management ships. The replacement reads from the synced raw_payload instead
    of PLAN_FEATURES. Call sites do not change.
    """
    plan = PLAN_FEATURES.get(plan_codename)
    if plan is not None and feature_key in plan:
        return plan[feature_key]
    return resolve_default(feature_key)
```

- [ ] **Step 6: Run tests to confirm they pass**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp /home/devadmin/inventory-management-system/services/api/tests $CONTAINER:/app/tests
docker cp /home/devadmin/inventory-management-system/services/api/app $CONTAINER:/app/app
docker compose exec api python -m pytest tests/billing/test_features_catalog.py -v
docker compose exec api rm -rf /app/tests /app/app
docker compose restart api
```
Expected: 6 passed.

(The `docker cp` then `restart` pattern is needed because the API container runs from a copied-in `/app` and we replaced it; a real deployment would hot-reload.)

- [ ] **Step 7: Commit**

```bash
git add services/api/app/billing/__init__.py \
        services/api/app/billing/features.py \
        services/api/app/billing/plans.py \
        services/api/tests/billing/__init__.py \
        services/api/tests/billing/test_features_catalog.py
git commit -m "feat(billing): add feature catalog + plan-feature mapping (config-as-code)"
```

---

### Task 3: Entitlements resolver (no caching yet)

**Files:**
- Create: `services/api/app/billing/entitlements.py`
- Create: `services/api/tests/billing/test_entitlements_resolver.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/billing/test_entitlements_resolver.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.models import Tenant, TenantFeatureOverride


@pytest.fixture()
def pro_tenant(db, tenant: Tenant) -> Tenant:
    return tenant


def _resolve(db, tenant: Tenant, plan_codename: str = "pro"):
    from app.billing.entitlements import resolve_for_tenant
    return resolve_for_tenant(db, tenant.id, plan_codename)


def test_resolver_returns_plan_value_when_no_override(db, pro_tenant: Tenant) -> None:
    ents = _resolve(db, pro_tenant, plan_codename="pro")
    assert ents.has("headless_api") is True
    assert ents.get("max_channels") == 5


def test_resolver_returns_default_for_unknown_plan(db, pro_tenant: Tenant) -> None:
    ents = _resolve(db, pro_tenant, plan_codename="totally-unknown")
    assert ents.has("headless_api") is False
    assert ents.get("max_channels") == 1


def test_override_beats_plan(db, pro_tenant: Tenant) -> None:
    db.add(TenantFeatureOverride(
        tenant_id=pro_tenant.id,
        feature_key="max_channels",
        value=42,
        reason="enterprise pilot",
    ))
    db.flush()

    ents = _resolve(db, pro_tenant, plan_codename="free")
    assert ents.get("max_channels") == 42


def test_expired_override_is_ignored(db, pro_tenant: Tenant) -> None:
    db.add(TenantFeatureOverride(
        tenant_id=pro_tenant.id,
        feature_key="headless_api",
        value=True,
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    ))
    db.flush()

    ents = _resolve(db, pro_tenant, plan_codename="free")
    assert ents.has("headless_api") is False


def test_future_expiring_override_still_applies(db, pro_tenant: Tenant) -> None:
    db.add(TenantFeatureOverride(
        tenant_id=pro_tenant.id,
        feature_key="headless_api",
        value=True,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    ))
    db.flush()

    ents = _resolve(db, pro_tenant, plan_codename="free")
    assert ents.has("headless_api") is True


def test_require_raises_when_feature_off(db, pro_tenant: Tenant) -> None:
    ents = _resolve(db, pro_tenant, plan_codename="free")
    with pytest.raises(HTTPException) as exc:
        ents.require("headless_api")
    assert exc.value.status_code == 403
    assert "plan_upgrade_required" in str(exc.value.detail)


def test_require_returns_silently_when_on(db, pro_tenant: Tenant) -> None:
    ents = _resolve(db, pro_tenant, plan_codename="pro")
    ents.require("headless_api")  # no exception


def test_limit_returns_numeric_value(db, pro_tenant: Tenant) -> None:
    ents = _resolve(db, pro_tenant, plan_codename="pro")
    assert ents.limit("max_channels") == 5


def test_limit_raises_for_non_numeric_feature(db, pro_tenant: Tenant) -> None:
    ents = _resolve(db, pro_tenant, plan_codename="pro")
    with pytest.raises(ValueError):
        ents.limit("headless_api")  # bool, not numeric
```

- [ ] **Step 2: Run test to confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp /home/devadmin/inventory-management-system/services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest tests/billing/test_entitlements_resolver.py -v
docker compose exec api rm -rf /app/tests
```
Expected: FAIL — `ImportError: cannot import name 'resolve_for_tenant' from 'app.billing.entitlements'`

- [ ] **Step 3: Implement the resolver**

Create `services/api/app/billing/entitlements.py`:

```python
"""Entitlements resolver — merges catalog defaults, plan values, and tenant overrides.

Resolution order (later sources override earlier):
    1. Catalog default (from features.py)
    2. Plan-codename value (from plans.py)
    3. Per-tenant override (from tenant_feature_overrides table; expired rows ignored)

Use ``resolve_for_tenant`` in tests and service code; in route handlers, prefer
the FastAPI dependency ``EntitlementsDep`` from billing.deps (Task 5).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing.features import (
    FEATURE_CATALOG,
    FeatureDefinition,
    ValueType,
    get_definition,
    resolve_default,
)
from app.billing.plans import resolve_plan_value
from app.models import TenantFeatureOverride


class Entitlements:
    """Resolved entitlements for a single tenant.

    Construct via ``resolve_for_tenant`` or ``Entitlements.from_values``.
    """

    def __init__(self, plan_codename: str, values: dict[str, Any]) -> None:
        self.plan_codename = plan_codename
        self._values = values

    @classmethod
    def from_values(cls, plan_codename: str, values: dict[str, Any]) -> "Entitlements":
        return cls(plan_codename, values)

    def get(self, key: str) -> Any:
        if key in self._values:
            return self._values[key]
        return resolve_default(key)

    def has(self, key: str) -> bool:
        """For boolean features. Raises if the feature is not boolean."""
        d = get_definition(key)
        if d is None:
            return False
        if d.value_type is not ValueType.BOOL:
            raise ValueError(f"has() called on non-boolean feature {key!r}")
        return bool(self.get(key))

    def limit(self, key: str) -> int:
        """For numeric limits. Raises if the feature is not numeric."""
        d = get_definition(key)
        if d is None:
            raise ValueError(f"unknown feature key {key!r}")
        if d.value_type is not ValueType.NUMERIC:
            raise ValueError(f"limit() called on non-numeric feature {key!r}")
        return int(self.get(key))

    def require(self, key: str) -> None:
        """Raise 403 if a boolean feature is off. No-op if on."""
        d = get_definition(key)
        if d is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"unknown feature {key!r}",
            )
        if d.value_type is ValueType.BOOL and not self.has(key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "plan_upgrade_required",
                    "required_feature": key,
                    "current_plan": self.plan_codename,
                },
            )

    def to_dict(self) -> dict[str, Any]:
        # Materialize all known keys (defaults + plan + overrides)
        out: dict[str, Any] = {}
        for f in FEATURE_CATALOG:
            out[f.key] = self.get(f.key)
        return out


def _load_overrides(db: Session, tenant_id: UUID) -> dict[str, Any]:
    """Load active (non-expired) per-tenant overrides keyed by feature_key."""
    now = datetime.now(UTC)
    rows = db.execute(
        select(TenantFeatureOverride).where(TenantFeatureOverride.tenant_id == tenant_id)
    ).scalars().all()
    out: dict[str, Any] = {}
    for r in rows:
        if r.expires_at is not None and r.expires_at <= now:
            continue
        out[r.feature_key] = r.value
    return out


def resolve_for_tenant(db: Session, tenant_id: UUID, plan_codename: str) -> Entitlements:
    """Resolve entitlements for a tenant. Returns a typed ``Entitlements`` view.

    Order: catalog default -> plan value -> override.
    """
    values: dict[str, Any] = {}

    # 1. Plan values (only for keys the plan explicitly sets; resolve_plan_value
    #    handles fallback to default per-key on .get(), so we materialize the
    #    full catalog here for cache stability)
    for f in FEATURE_CATALOG:
        values[f.key] = resolve_plan_value(plan_codename, f.key)

    # 2. Active per-tenant overrides
    overrides = _load_overrides(db, tenant_id)
    values.update(overrides)

    return Entitlements.from_values(plan_codename, values)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp /home/devadmin/inventory-management-system/services/api/tests $CONTAINER:/app/tests
docker cp /home/devadmin/inventory-management-system/services/api/app $CONTAINER:/app/app
docker compose restart api
docker compose exec api python -m pytest tests/billing/test_entitlements_resolver.py -v
docker compose exec api rm -rf /app/tests /app/app
```
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/billing/entitlements.py \
        services/api/tests/billing/test_entitlements_resolver.py
git commit -m "feat(billing): add entitlements resolver with override + plan + default merge"
```

---

### Task 4: Add Redis caching to the resolver

**Files:**
- Modify: `services/api/app/billing/entitlements.py`
- Create: `services/api/tests/billing/test_entitlements_cache.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/billing/test_entitlements_cache.py`:

```python
from __future__ import annotations

import json

import pytest

from app.models import Tenant, TenantFeatureOverride
from app.worker.queue import redis_conn


def _cache_key(tenant_id, plan: str) -> str:
    return f"ents:v1:{tenant_id}:{plan}"


def _purge(tenant_id):
    r = redis_conn()
    for k in r.scan_iter(f"ents:v1:{tenant_id}:*"):
        r.delete(k)


@pytest.fixture(autouse=True)
def clear_cache(tenant: Tenant):
    _purge(tenant.id)
    yield
    _purge(tenant.id)


def test_resolved_value_is_cached_after_first_call(db, tenant: Tenant) -> None:
    from app.billing.entitlements import resolve_for_tenant

    resolve_for_tenant(db, tenant.id, "pro")
    raw = redis_conn().get(_cache_key(tenant.id, "pro"))
    assert raw is not None
    payload = json.loads(raw)
    assert payload["plan_codename"] == "pro"
    assert payload["values"]["headless_api"] is True


def test_cache_hit_does_not_query_db(db, tenant: Tenant, monkeypatch) -> None:
    from app.billing import entitlements as ents_mod

    # Prime the cache
    ents_mod.resolve_for_tenant(db, tenant.id, "pro")

    # Now any DB call to _load_overrides would be a bug
    called = {"count": 0}
    real_loader = ents_mod._load_overrides

    def spy(*args, **kwargs):
        called["count"] += 1
        return real_loader(*args, **kwargs)

    monkeypatch.setattr(ents_mod, "_load_overrides", spy)
    ents_mod.resolve_for_tenant(db, tenant.id, "pro")
    assert called["count"] == 0, "Expected cache hit, but DB loader was invoked"


def test_invalidate_removes_cached_entries(db, tenant: Tenant) -> None:
    from app.billing.entitlements import invalidate_cache, resolve_for_tenant

    resolve_for_tenant(db, tenant.id, "pro")
    resolve_for_tenant(db, tenant.id, "free")
    assert redis_conn().get(_cache_key(tenant.id, "pro")) is not None
    assert redis_conn().get(_cache_key(tenant.id, "free")) is not None

    invalidate_cache(tenant.id)
    assert redis_conn().get(_cache_key(tenant.id, "pro")) is None
    assert redis_conn().get(_cache_key(tenant.id, "free")) is None


def test_invalidate_called_after_override_write(db, tenant: Tenant) -> None:
    from app.billing.entitlements import resolve_for_tenant

    # Prime cache with current state (no overrides → free plan returns False)
    ents = resolve_for_tenant(db, tenant.id, "free")
    assert ents.has("headless_api") is False

    # Add override but DON'T invalidate — cache still says False
    db.add(TenantFeatureOverride(
        tenant_id=tenant.id, feature_key="headless_api", value=True,
    ))
    db.flush()

    cached = resolve_for_tenant(db, tenant.id, "free")
    assert cached.has("headless_api") is False  # stale because not invalidated

    # Invalidate, then re-resolve — now reflects the override
    from app.billing.entitlements import invalidate_cache
    invalidate_cache(tenant.id)
    fresh = resolve_for_tenant(db, tenant.id, "free")
    assert fresh.has("headless_api") is True
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp /home/devadmin/inventory-management-system/services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest tests/billing/test_entitlements_cache.py -v
docker compose exec api rm -rf /app/tests
```
Expected: FAIL — `ImportError: cannot import name 'invalidate_cache'` and the caching tests fail because nothing is cached.

- [ ] **Step 3: Add Redis caching to the resolver**

Modify `services/api/app/billing/entitlements.py`. Add these imports at the top of the file (with the other imports):

```python
import json
import logging

from app.worker.queue import redis_conn

logger = logging.getLogger(__name__)

CACHE_PREFIX = "ents:v1"
CACHE_TTL_SECONDS = 300  # 5 minutes — invalidations on write keep this tighter
```

Then replace the `resolve_for_tenant` function with a cached version, and add `invalidate_cache`. The full new function bodies:

```python
def _cache_key(tenant_id: UUID, plan_codename: str) -> str:
    return f"{CACHE_PREFIX}:{tenant_id}:{plan_codename}"


def resolve_for_tenant(db: Session, tenant_id: UUID, plan_codename: str) -> Entitlements:
    """Resolve entitlements for a tenant. Cache-aware.

    Cache hits skip DB. Misses load overrides + merge, then write through.
    Cache invalidation is the writer's responsibility — see ``invalidate_cache``.
    """
    cached = _read_cache(tenant_id, plan_codename)
    if cached is not None:
        return cached

    values: dict[str, Any] = {}
    for f in FEATURE_CATALOG:
        values[f.key] = resolve_plan_value(plan_codename, f.key)

    overrides = _load_overrides(db, tenant_id)
    values.update(overrides)

    ents = Entitlements.from_values(plan_codename, values)
    _write_cache(tenant_id, plan_codename, ents)
    return ents


def invalidate_cache(tenant_id: UUID) -> None:
    """Drop all cached entitlement entries for a tenant.

    Call this from any code path that writes a tenant_feature_overrides row.
    """
    try:
        r = redis_conn()
        keys = list(r.scan_iter(f"{CACHE_PREFIX}:{tenant_id}:*"))
        if keys:
            r.delete(*keys)
    except Exception:
        logger.warning("Failed to invalidate entitlement cache for %s", tenant_id, exc_info=True)


def _read_cache(tenant_id: UUID, plan_codename: str) -> Entitlements | None:
    try:
        raw = redis_conn().get(_cache_key(tenant_id, plan_codename))
        if raw is None:
            return None
        payload = json.loads(raw)
        return Entitlements.from_values(payload["plan_codename"], payload["values"])
    except Exception:
        logger.warning("Entitlement cache read failed for %s/%s", tenant_id, plan_codename, exc_info=True)
        return None


def _write_cache(tenant_id: UUID, plan_codename: str, ents: Entitlements) -> None:
    try:
        payload = json.dumps({
            "plan_codename": ents.plan_codename,
            "values": ents._values,  # noqa: SLF001 — controlled serialization
        })
        redis_conn().setex(_cache_key(tenant_id, plan_codename), CACHE_TTL_SECONDS, payload)
    except Exception:
        logger.warning("Entitlement cache write failed for %s/%s", tenant_id, plan_codename, exc_info=True)
```

- [ ] **Step 4: Run all billing tests to confirm pass**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp /home/devadmin/inventory-management-system/services/api/tests $CONTAINER:/app/tests
docker cp /home/devadmin/inventory-management-system/services/api/app $CONTAINER:/app/app
docker compose restart api
docker compose exec api python -m pytest tests/billing -v
docker compose exec api rm -rf /app/tests /app/app
```
Expected: all 19 tests pass (6 catalog + 9 resolver + 4 cache).

- [ ] **Step 5: Commit**

```bash
git add services/api/app/billing/entitlements.py \
        services/api/tests/billing/test_entitlements_cache.py
git commit -m "feat(billing): cache entitlement resolution in Redis with explicit invalidation"
```

---

### Task 5: FastAPI dependency + service-layer API

**Files:**
- Create: `services/api/app/billing/deps.py`
- Create: `services/api/tests/billing/test_entitlements_dep.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/billing/test_entitlements_dep.py`:

```python
from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models import Tenant, TenantLicenseCache


@pytest.fixture()
def licensed_tenant(db, tenant: Tenant) -> Tenant:
    from datetime import UTC, datetime
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


def _build_app_with_route():
    """Build a minimal FastAPI app with a single route gated by EntitlementsDep."""
    from app.billing.deps import EntitlementsDep
    from app.billing.entitlements import Entitlements

    app = FastAPI()

    @app.get("/test/headless-only")
    def headless_only(ents: EntitlementsDep) -> dict:
        ents.require("headless_api")
        return {"ok": True, "plan": ents.plan_codename}

    @app.get("/test/limit")
    def limit_route(ents: EntitlementsDep) -> dict:
        return {"max_channels": ents.limit("max_channels")}

    return app


def _stub_admin(app, tenant_id):
    """Override admin auth so the test client gets a known context.

    Uses is_legacy_token=False because license_deps._load_license_context
    short-circuits to plan_codename="legacy" when is_legacy_token=True, which
    would bypass the cache lookup we need EntitlementsDep to consult. Permission
    checks aren't a concern here because the routes under test don't use
    require_permission().
    """
    from app.auth.admin_deps import AdminContext, require_admin_context

    fake_ctx = AdminContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id,
        role="tenant_admin",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset(),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    return fake_ctx


def test_entitlements_dep_resolves_for_authenticated_tenant(licensed_tenant: Tenant) -> None:
    """A request from a tenant on 'pro' should pass the headless_api gate."""
    app = _build_app_with_route()
    _stub_admin(app, licensed_tenant.id)

    client = TestClient(app)
    resp = client.get("/test/headless-only")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "plan": "pro"}


def test_entitlements_dep_rejects_when_feature_off(db, tenant: Tenant) -> None:
    """A 'free' plan tenant calling a 'headless_api'-gated route gets 403 plan_upgrade_required."""
    from datetime import UTC, datetime

    db.add(TenantLicenseCache(
        tenant_id=tenant.id,
        subscription_status="active",
        plan_codename="free",
        max_shops=1,
        max_employees=2,
        storage_limit_mb=500,
        last_synced_at=datetime.now(UTC),
    ))
    db.commit()

    app = _build_app_with_route()
    _stub_admin(app, tenant.id)

    client = TestClient(app)
    resp = client.get("/test/headless-only")
    assert resp.status_code == 403
    body = resp.json()
    assert body["detail"]["error"] == "plan_upgrade_required"
    assert body["detail"]["required_feature"] == "headless_api"
    assert body["detail"]["current_plan"] == "free"


def test_entitlements_dep_returns_numeric_limit(licensed_tenant: Tenant) -> None:
    app = _build_app_with_route()
    _stub_admin(app, licensed_tenant.id)

    client = TestClient(app)
    resp = client.get("/test/limit")
    assert resp.status_code == 200
    assert resp.json() == {"max_channels": 5}
```

- [ ] **Step 2: Run test to confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp /home/devadmin/inventory-management-system/services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest tests/billing/test_entitlements_dep.py -v
docker compose exec api rm -rf /app/tests
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.billing.deps'`

- [ ] **Step 3: Implement the FastAPI dependency**

Create `services/api/app/billing/deps.py`:

```python
"""FastAPI dependencies that expose entitlements and engineering flags to route handlers.

Usage in a route::

    from app.billing.deps import EntitlementsDep

    @router.get("/v1/admin/headless/products")
    def list_products(ents: EntitlementsDep, ...) -> ...:
        ents.require("headless_api")     # 403 if plan does not include
        return ...

For numeric limits::

    if existing_count >= ents.limit("max_channels"):
        raise HTTPException(...)

The dependency depends on the same admin auth chain as ``LicenseContextDep``
and reuses the cached license-context's plan_codename — no extra DB hit.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.auth.license_deps import LicenseContext, LicenseContextDep
from app.billing.entitlements import Entitlements, resolve_for_tenant
from app.db.admin_deps_db import get_db_admin


def _load_entitlements(
    license_ctx: LicenseContextDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> Entitlements:
    return resolve_for_tenant(db, license_ctx.tenant_id, license_ctx.plan_codename)


EntitlementsDep = Annotated[Entitlements, Depends(_load_entitlements)]
```

- [ ] **Step 4: Run test to confirm pass**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp /home/devadmin/inventory-management-system/services/api/tests $CONTAINER:/app/tests
docker cp /home/devadmin/inventory-management-system/services/api/app $CONTAINER:/app/app
docker compose restart api
docker compose exec api python -m pytest tests/billing/test_entitlements_dep.py -v
docker compose exec api rm -rf /app/tests /app/app
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/billing/deps.py \
        services/api/tests/billing/test_entitlements_dep.py
git commit -m "feat(billing): add EntitlementsDep FastAPI dependency"
```

---

### Task 6: Engineering rollout flag resolver

**Files:**
- Create: `services/api/app/billing/flags.py`
- Create: `services/api/tests/billing/test_flags_resolver.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/billing/test_flags_resolver.py`:

```python
from __future__ import annotations

import uuid

import pytest

from app.models import FeatureFlag, Tenant
from app.worker.queue import redis_conn


@pytest.fixture(autouse=True)
def clear_flag_cache():
    r = redis_conn()
    for k in r.scan_iter("flag:v1:*"):
        r.delete(k)
    yield
    for k in r.scan_iter("flag:v1:*"):
        r.delete(k)


def _flag(db, key: str, default: bool = False, rules: dict | None = None) -> FeatureFlag:
    f = FeatureFlag(key=key, default_state=default, rollout_rules=rules)
    db.add(f)
    db.flush()
    return f


def test_unknown_flag_is_off(db, tenant: Tenant) -> None:
    from app.billing.flags import is_enabled
    assert is_enabled(db, tenant.id, "does-not-exist") is False


def test_flag_default_state_off(db, tenant: Tenant) -> None:
    from app.billing.flags import is_enabled
    _flag(db, "flag-a", default=False)
    assert is_enabled(db, tenant.id, "flag-a") is False


def test_flag_default_state_on(db, tenant: Tenant) -> None:
    from app.billing.flags import is_enabled
    _flag(db, "flag-b", default=True)
    assert is_enabled(db, tenant.id, "flag-b") is True


def test_allowlist_takes_effect_when_default_off(db, tenant: Tenant) -> None:
    from app.billing.flags import is_enabled
    _flag(db, "flag-c", default=False, rules={"allowlist": [str(tenant.id)]})
    assert is_enabled(db, tenant.id, "flag-c") is True

    other_tenant = uuid.uuid4()
    assert is_enabled(db, other_tenant, "flag-c") is False


def test_denylist_takes_effect_when_default_on(db, tenant: Tenant) -> None:
    from app.billing.flags import is_enabled
    _flag(db, "flag-d", default=True, rules={"denylist": [str(tenant.id)]})
    assert is_enabled(db, tenant.id, "flag-d") is False


def test_percent_rollout_is_deterministic_per_tenant(db, tenant: Tenant) -> None:
    """A given tenant_id either bucket-hits or not for a given flag — not random."""
    from app.billing.flags import is_enabled
    _flag(db, "flag-e", default=False, rules={"percent": 50})
    a = is_enabled(db, tenant.id, "flag-e")
    b = is_enabled(db, tenant.id, "flag-e")
    assert a == b


def test_percent_rollout_zero_is_off(db, tenant: Tenant) -> None:
    from app.billing.flags import is_enabled
    _flag(db, "flag-f", default=False, rules={"percent": 0})
    assert is_enabled(db, tenant.id, "flag-f") is False


def test_percent_rollout_hundred_is_on(db, tenant: Tenant) -> None:
    from app.billing.flags import is_enabled
    _flag(db, "flag-g", default=False, rules={"percent": 100})
    assert is_enabled(db, tenant.id, "flag-g") is True


def test_invalidate_clears_cached_value(db, tenant: Tenant) -> None:
    from app.billing.flags import is_enabled, invalidate_flag_cache
    flag = _flag(db, "flag-h", default=False)
    assert is_enabled(db, tenant.id, "flag-h") is False  # populates cache

    flag.default_state = True
    db.flush()

    # Stale cache still says False until invalidated
    assert is_enabled(db, tenant.id, "flag-h") is False
    invalidate_flag_cache("flag-h")
    assert is_enabled(db, tenant.id, "flag-h") is True
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp /home/devadmin/inventory-management-system/services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest tests/billing/test_flags_resolver.py -v
docker compose exec api rm -rf /app/tests
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.billing.flags'`

- [ ] **Step 3: Implement the flag resolver**

Create `services/api/app/billing/flags.py`:

```python
"""Engineering rollout flags — separate from plan entitlements.

Flags answer "is this feature rolled out yet?", entitlements answer "does this
plan include it?". Layer in code as ``ents.require(...)`` THEN
``flags.is_enabled(...)`` — a 403 (commercial) takes precedence over a 503
(rollout).

Rules format::

    {
      "allowlist": ["<tenant-uuid>", ...],
      "denylist": ["<tenant-uuid>", ...],
      "percent":  0..100
    }

Resolution: an allowlist match forces ON, denylist match forces OFF, otherwise
the bucket from a stable hash of (tenant_id, flag_key) decides percent rollout,
falling back to ``default_state``.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FeatureFlag
from app.worker.queue import redis_conn

logger = logging.getLogger(__name__)

CACHE_PREFIX = "flag:v1"
CACHE_TTL_SECONDS = 60  # short — flags change during rollouts


def _bucket(tenant_id: UUID, flag_key: str) -> int:
    """Stable 0..99 bucket. Same tenant + same flag = same bucket."""
    h = hashlib.sha1(f"{tenant_id}:{flag_key}".encode()).digest()
    return h[0] % 100


def _eval_rules(tenant_id: UUID, flag: FeatureFlag) -> bool:
    rules: dict[str, Any] = flag.rollout_rules or {}
    tid = str(tenant_id)

    if tid in (rules.get("denylist") or []):
        return False
    if tid in (rules.get("allowlist") or []):
        return True

    pct = rules.get("percent")
    if isinstance(pct, int) and 0 <= pct <= 100:
        if _bucket(tenant_id, flag.key) < pct:
            return True
        if pct == 100:
            return True
        # Below percent threshold: fall through to default_state
        # (matters when default_state=True and percent is acting as a denylist gate)
    return flag.default_state


def is_enabled(db: Session, tenant_id: UUID, flag_key: str) -> bool:
    """Return True if the flag is enabled for the tenant."""
    cached = _read_cache(flag_key)
    if cached is not None:
        flag = cached
    else:
        flag = db.execute(
            select(FeatureFlag).where(FeatureFlag.key == flag_key)
        ).scalar_one_or_none()
        if flag is None:
            return False
        _write_cache(flag)

    return _eval_rules(tenant_id, flag)


def invalidate_flag_cache(flag_key: str) -> None:
    try:
        redis_conn().delete(f"{CACHE_PREFIX}:{flag_key}")
    except Exception:
        logger.warning("Failed to invalidate flag cache for %s", flag_key, exc_info=True)


def _read_cache(flag_key: str) -> FeatureFlag | None:
    try:
        raw = redis_conn().get(f"{CACHE_PREFIX}:{flag_key}")
        if raw is None:
            return None
        payload = json.loads(raw)
        # Construct a transient FeatureFlag (not attached to session) for evaluation
        f = FeatureFlag()
        f.key = payload["key"]
        f.default_state = payload["default_state"]
        f.rollout_rules = payload.get("rollout_rules")
        return f
    except Exception:
        logger.warning("Flag cache read failed for %s", flag_key, exc_info=True)
        return None


def _write_cache(flag: FeatureFlag) -> None:
    try:
        payload = json.dumps({
            "key": flag.key,
            "default_state": flag.default_state,
            "rollout_rules": flag.rollout_rules,
        })
        redis_conn().setex(f"{CACHE_PREFIX}:{flag.key}", CACHE_TTL_SECONDS, payload)
    except Exception:
        logger.warning("Flag cache write failed for %s", flag.key, exc_info=True)
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp /home/devadmin/inventory-management-system/services/api/tests $CONTAINER:/app/tests
docker cp /home/devadmin/inventory-management-system/services/api/app $CONTAINER:/app/app
docker compose restart api
docker compose exec api python -m pytest tests/billing/test_flags_resolver.py -v
docker compose exec api rm -rf /app/tests /app/app
```
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/billing/flags.py \
        services/api/tests/billing/test_flags_resolver.py
git commit -m "feat(billing): add engineering feature-flag resolver with allowlist/denylist/percent rollout"
```

---

### Task 7: Admin CRUD endpoints — tenant_feature_overrides

**Files:**
- Create: `services/api/app/routers/admin_entitlements.py`
- Modify: `services/api/app/main.py`
- Create: `services/api/tests/routers/test_admin_entitlements_overrides.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/routers/test_admin_entitlements_overrides.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Tenant, TenantFeatureOverride
from app.worker.queue import redis_conn


def _purge_cache(tenant_id):
    r = redis_conn()
    for k in r.scan_iter(f"ents:v1:{tenant_id}:*"):
        r.delete(k)


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    """Stub admin auth: operator with the entitlements:manage permission."""
    from app.auth.admin_deps import AdminContext, require_admin_context

    fake_ctx = AdminContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        role="staff",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset({"entitlements:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    yield {}
    app.dependency_overrides.clear()


def test_create_override(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/entitlements/overrides", json={
        "feature_key": "headless_api",
        "value": True,
        "reason": "Beta access",
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["feature_key"] == "headless_api"
    assert body["value"] is True
    assert body["reason"] == "Beta access"


def test_create_override_invalidates_cache(db, tenant: Tenant, auth_headers) -> None:
    from app.billing.entitlements import resolve_for_tenant
    _purge_cache(tenant.id)

    # Prime cache with current state
    resolve_for_tenant(db, tenant.id, "free")
    assert redis_conn().keys(f"ents:v1:{tenant.id}:*")

    # Create override via API
    client = TestClient(app)
    resp = client.post("/v1/admin/entitlements/overrides", json={
        "feature_key": "headless_api", "value": True,
    }, headers=auth_headers)
    assert resp.status_code == 201

    # Cache should be cleared
    assert not redis_conn().keys(f"ents:v1:{tenant.id}:*")


def test_list_overrides(db, tenant: Tenant, auth_headers) -> None:
    db.add(TenantFeatureOverride(
        tenant_id=tenant.id, feature_key="headless_api", value=True,
    ))
    db.add(TenantFeatureOverride(
        tenant_id=tenant.id, feature_key="max_channels", value=42,
    ))
    db.commit()

    client = TestClient(app)
    resp = client.get("/v1/admin/entitlements/overrides", headers=auth_headers)
    assert resp.status_code == 200
    keys = {o["feature_key"] for o in resp.json()}
    assert keys == {"headless_api", "max_channels"}


def test_delete_override(db, tenant: Tenant, auth_headers) -> None:
    o = TenantFeatureOverride(
        tenant_id=tenant.id, feature_key="headless_api", value=True,
    )
    db.add(o)
    db.commit()

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/entitlements/overrides/{o.id}", headers=auth_headers)
    assert resp.status_code == 204

    # Confirm gone
    resp = client.get("/v1/admin/entitlements/overrides", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_unknown_feature_key_rejected(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/entitlements/overrides", json={
        "feature_key": "made-up-feature", "value": True,
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert "unknown feature" in resp.json()["detail"].lower()


def test_create_with_expiry(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    expires = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    resp = client.post("/v1/admin/entitlements/overrides", json={
        "feature_key": "headless_api",
        "value": True,
        "expires_at": expires,
    }, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["expires_at"] is not None
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp /home/devadmin/inventory-management-system/services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest tests/routers/test_admin_entitlements_overrides.py -v
docker compose exec api rm -rf /app/tests
```
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routers.admin_entitlements'`

- [ ] **Step 3: Implement the router (overrides only for now; flags in Task 8)**

Create `services/api/app/routers/admin_entitlements.py`:

```python
"""Admin endpoints for managing entitlements: per-tenant feature overrides + engineering flags.

Auth: requires ``entitlements:manage`` permission. Granted to ``tenant_admin`` by
default in the migration, but in practice this is operator territory — the
admin web should hide the UI behind a separate feature gate later.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.billing.entitlements import invalidate_cache
from app.billing.features import get_definition
from app.db.admin_deps_db import get_db_admin
from app.models import TenantFeatureOverride

router = APIRouter(
    prefix="/v1/admin/entitlements",
    tags=["Admin Entitlements"],
    dependencies=[require_permission("entitlements:manage")],
)


# --- Schemas ---

class TenantFeatureOverrideIn(BaseModel):
    feature_key: str = Field(min_length=1, max_length=128)
    value: Any
    reason: str | None = None
    expires_at: datetime | None = None


class TenantFeatureOverrideOut(BaseModel):
    id: UUID
    tenant_id: UUID
    feature_key: str
    value: Any
    reason: str | None
    expires_at: datetime | None
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


@router.get("/overrides", response_model=list[TenantFeatureOverrideOut])
def list_overrides(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[TenantFeatureOverride]:
    tenant_id = _require_tenant(ctx)
    rows = db.execute(
        select(TenantFeatureOverride).where(TenantFeatureOverride.tenant_id == tenant_id)
    ).scalars().all()
    return list(rows)


@router.post("/overrides", response_model=TenantFeatureOverrideOut, status_code=status.HTTP_201_CREATED)
def create_override(
    body: TenantFeatureOverrideIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> TenantFeatureOverride:
    tenant_id = _require_tenant(ctx)

    if get_definition(body.feature_key) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown feature key: {body.feature_key}",
        )

    # Upsert: replace any existing override on the same key
    existing = db.execute(
        select(TenantFeatureOverride).where(
            TenantFeatureOverride.tenant_id == tenant_id,
            TenantFeatureOverride.feature_key == body.feature_key,
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.value = body.value
        existing.reason = body.reason
        existing.expires_at = body.expires_at
        existing.updated_at = datetime.now(UTC)
        row = existing
    else:
        row = TenantFeatureOverride(
            tenant_id=tenant_id,
            feature_key=body.feature_key,
            value=body.value,
            reason=body.reason,
            expires_at=body.expires_at,
        )
        db.add(row)

    db.commit()
    db.refresh(row)
    invalidate_cache(tenant_id)
    return row


@router.delete("/overrides/{override_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_override(
    override_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    row = db.get(TenantFeatureOverride, override_id)
    if row is None or row.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Override not found")
    db.delete(row)
    db.commit()
    invalidate_cache(tenant_id)
```

- [ ] **Step 4: Mount the router in main.py**

In `services/api/app/main.py`, add `admin_entitlements` to the imports near the top of the routers list:

```python
from app.routers import (
    ...,
    admin_entitlements,
    ...,
)
```

(Keep alphabetical order: insert between `admin_customers` and `admin_inventory` if alphabetized that way; otherwise follow existing order.)

Then in the `include_router` block:

```python
app.include_router(admin_entitlements.router)
```

- [ ] **Step 5: Run tests to confirm pass**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp /home/devadmin/inventory-management-system/services/api/tests $CONTAINER:/app/tests
docker cp /home/devadmin/inventory-management-system/services/api/app $CONTAINER:/app/app
docker compose restart api
docker compose exec api python -m pytest tests/routers/test_admin_entitlements_overrides.py tests/test_admin_console_contracts.py::test_tenant_feature_override_out_schema -v
docker compose exec api rm -rf /app/tests /app/app
```
Expected: 6 router tests + 1 contract test all pass.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/routers/admin_entitlements.py \
        services/api/app/main.py \
        services/api/tests/routers/test_admin_entitlements_overrides.py
git commit -m "feat(billing): admin CRUD endpoints for tenant_feature_overrides"
```

---

### Task 8: Admin CRUD endpoints — feature_flags

**Files:**
- Modify: `services/api/app/routers/admin_entitlements.py`
- Create: `services/api/tests/routers/test_admin_entitlements_flags.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/routers/test_admin_entitlements_flags.py`:

```python
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import FeatureFlag, Tenant
from app.worker.queue import redis_conn


@pytest.fixture(autouse=True)
def clear_flag_cache():
    r = redis_conn()
    for k in r.scan_iter("flag:v1:*"):
        r.delete(k)
    yield


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context

    fake_ctx = AdminContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant.id,
        role="staff",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset({"entitlements:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    yield {}
    app.dependency_overrides.clear()


def test_create_flag(db, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/entitlements/flags", json={
        "key": "stock_reservations_enabled",
        "default_state": False,
        "rollout_rules": {"percent": 10},
        "description": "Phase 0 reservation engine",
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["key"] == "stock_reservations_enabled"
    assert body["default_state"] is False
    assert body["rollout_rules"]["percent"] == 10


def test_list_flags(db, auth_headers) -> None:
    db.add(FeatureFlag(key="flag-a", default_state=True))
    db.add(FeatureFlag(key="flag-b", default_state=False))
    db.commit()

    client = TestClient(app)
    resp = client.get("/v1/admin/entitlements/flags", headers=auth_headers)
    assert resp.status_code == 200
    keys = {f["key"] for f in resp.json()}
    assert keys >= {"flag-a", "flag-b"}


def test_update_flag_invalidates_cache(db, auth_headers) -> None:
    from app.billing.flags import is_enabled

    flag = FeatureFlag(key="flag-toggle", default_state=False)
    db.add(flag)
    db.commit()
    db.refresh(flag)

    # Prime cache
    assert is_enabled(db, uuid.uuid4(), "flag-toggle") is False

    client = TestClient(app)
    resp = client.patch(f"/v1/admin/entitlements/flags/{flag.id}", json={
        "default_state": True,
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["default_state"] is True

    # Cache should be invalidated → next read sees new value
    assert is_enabled(db, uuid.uuid4(), "flag-toggle") is True


def test_delete_flag(db, auth_headers) -> None:
    flag = FeatureFlag(key="flag-doomed", default_state=False)
    db.add(flag)
    db.commit()
    db.refresh(flag)

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/entitlements/flags/{flag.id}", headers=auth_headers)
    assert resp.status_code == 204


def test_duplicate_key_rejected(db, auth_headers) -> None:
    db.add(FeatureFlag(key="flag-dup", default_state=False))
    db.commit()

    client = TestClient(app)
    resp = client.post("/v1/admin/entitlements/flags", json={
        "key": "flag-dup", "default_state": True,
    }, headers=auth_headers)
    assert resp.status_code == 409
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp /home/devadmin/inventory-management-system/services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest tests/routers/test_admin_entitlements_flags.py -v
docker compose exec api rm -rf /app/tests
```
Expected: FAIL — endpoints don't exist.

- [ ] **Step 3: Add flag endpoints to the router**

Append to `services/api/app/routers/admin_entitlements.py`:

```python
# === Engineering flags ===

from app.billing.flags import invalidate_flag_cache
from app.models import FeatureFlag


class FeatureFlagIn(BaseModel):
    key: str = Field(min_length=1, max_length=128)
    default_state: bool = False
    rollout_rules: dict | None = None
    description: str | None = None


class FeatureFlagPatch(BaseModel):
    default_state: bool | None = None
    rollout_rules: dict | None = None
    description: str | None = None


# NOTE: `FeatureFlagOut` is already defined in this file (added during Task 7
# so the contract test in test_admin_console_contracts.py could turn green).
# Do NOT redefine it here.


@router.get("/flags", response_model=list[FeatureFlagOut])
def list_flags(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[FeatureFlag]:
    rows = db.execute(select(FeatureFlag)).scalars().all()
    return list(rows)


@router.post("/flags", response_model=FeatureFlagOut, status_code=status.HTTP_201_CREATED)
def create_flag(
    body: FeatureFlagIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> FeatureFlag:
    existing = db.execute(
        select(FeatureFlag).where(FeatureFlag.key == body.key)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Flag with key {body.key!r} already exists",
        )
    row = FeatureFlag(
        key=body.key,
        default_state=body.default_state,
        rollout_rules=body.rollout_rules,
        description=body.description,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    invalidate_flag_cache(body.key)
    return row


@router.patch("/flags/{flag_id}", response_model=FeatureFlagOut)
def update_flag(
    flag_id: UUID,
    body: FeatureFlagPatch,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> FeatureFlag:
    row = db.get(FeatureFlag, flag_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flag not found")

    if body.default_state is not None:
        row.default_state = body.default_state
    if body.rollout_rules is not None:
        row.rollout_rules = body.rollout_rules
    if body.description is not None:
        row.description = body.description

    db.commit()
    db.refresh(row)
    invalidate_flag_cache(row.key)
    return row


@router.delete("/flags/{flag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_flag(
    flag_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    row = db.get(FeatureFlag, flag_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flag not found")
    key = row.key
    db.delete(row)
    db.commit()
    invalidate_flag_cache(key)
```

- [ ] **Step 4: Run tests to confirm pass**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp /home/devadmin/inventory-management-system/services/api/tests $CONTAINER:/app/tests
docker cp /home/devadmin/inventory-management-system/services/api/app $CONTAINER:/app/app
docker compose restart api
docker compose exec api python -m pytest tests/routers/test_admin_entitlements_flags.py tests/test_admin_console_contracts.py::test_feature_flag_out_schema -v
docker compose exec api rm -rf /app/tests /app/app
```
Expected: 5 router tests + 1 contract test pass.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/routers/admin_entitlements.py \
        services/api/tests/routers/test_admin_entitlements_flags.py
git commit -m "feat(billing): admin CRUD endpoints for engineering feature flags"
```

---

### Task 9: Integration smoke test — gate a real route end-to-end

**Files:**
- Create: `services/api/tests/integration/test_entitlements_e2e.py`

This task does not add product code — only an integration test that exercises the full chain (license cache → license_deps → entitlements dep → 403 / 200) on a representative route. We use the existing `admin_billing.py` endpoints as the route under test (already wired to `LicenseContextDep`); we don't need to add a gate to it. Instead, we wire a temporary route into the app at test-time and confirm the contract.

- [ ] **Step 1: Write the integration test**

Create `services/api/tests/integration/__init__.py` if it doesn't already exist (empty file), then create `services/api/tests/integration/test_entitlements_e2e.py`:

```python
"""End-to-end smoke test for the entitlements stack.

Exercises: TenantLicenseCache -> _load_license_context (license_deps) ->
_load_entitlements (billing.deps) -> Entitlements.require -> HTTP response.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models import Tenant, TenantFeatureOverride, TenantLicenseCache
from app.worker.queue import redis_conn


def _purge(tenant_id):
    r = redis_conn()
    for k in r.scan_iter(f"ents:v1:{tenant_id}:*"):
        r.delete(k)


@pytest.fixture(autouse=True)
def cache_clean(tenant: Tenant):
    _purge(tenant.id)
    yield
    _purge(tenant.id)


def _seed_license(db, tenant_id, plan_codename: str) -> None:
    db.add(TenantLicenseCache(
        tenant_id=tenant_id,
        subscription_status="active",
        plan_codename=plan_codename,
        max_shops=999,
        max_employees=999,
        storage_limit_mb=99999,
        last_synced_at=datetime.now(UTC),
    ))
    db.commit()


def _build_app(tenant_id):
    """Build a minimal FastAPI app with auth override + a gated route."""
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.billing.deps import EntitlementsDep

    app = FastAPI()
    app.dependency_overrides[require_admin_context] = lambda: AdminContext(
        user_id=uuid.uuid4(),
        tenant_id=tenant_id,
        role="tenant_admin",
        role_id=None,
        is_legacy_token=True,
        permissions=frozenset(),
    )

    @app.get("/probe/headless")
    def probe(ents: EntitlementsDep):
        ents.require("headless_api")
        return {"plan": ents.plan_codename, "max_channels": ents.limit("max_channels")}

    return app


def test_pro_plan_gets_through(db, tenant: Tenant) -> None:
    _seed_license(db, tenant.id, "pro")
    app = _build_app(tenant.id)
    resp = TestClient(app).get("/probe/headless")
    assert resp.status_code == 200
    assert resp.json() == {"plan": "pro", "max_channels": 5}


def test_free_plan_blocked_with_structured_error(db, tenant: Tenant) -> None:
    _seed_license(db, tenant.id, "free")
    app = _build_app(tenant.id)
    resp = TestClient(app).get("/probe/headless")
    assert resp.status_code == 403
    body = resp.json()
    assert body["detail"]["error"] == "plan_upgrade_required"
    assert body["detail"]["required_feature"] == "headless_api"
    assert body["detail"]["current_plan"] == "free"


def test_override_unblocks_a_free_plan(db, tenant: Tenant) -> None:
    _seed_license(db, tenant.id, "free")
    db.add(TenantFeatureOverride(
        tenant_id=tenant.id,
        feature_key="headless_api",
        value=True,
        reason="Beta access",
    ))
    db.commit()

    app = _build_app(tenant.id)
    resp = TestClient(app).get("/probe/headless")
    assert resp.status_code == 200
    assert resp.json()["plan"] == "free"  # plan codename unchanged
```

- [ ] **Step 2: Run the integration test**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp /home/devadmin/inventory-management-system/services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest tests/integration/test_entitlements_e2e.py -v
docker compose exec api rm -rf /app/tests
```
Expected: 3 passed.

- [ ] **Step 3: Run the full billing test suite as a final check**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp /home/devadmin/inventory-management-system/services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest tests/billing tests/integration/test_entitlements_e2e.py tests/routers/test_admin_entitlements_overrides.py tests/routers/test_admin_entitlements_flags.py tests/test_admin_console_contracts.py::test_tenant_feature_override_out_schema tests/test_admin_console_contracts.py::test_feature_flag_out_schema -v
docker compose exec api rm -rf /app/tests
```
Expected: all green — 6 catalog + 9 resolver + 4 cache + 3 dep + 9 flag-resolver + 6 override-router + 5 flag-router + 3 e2e + 2 contract = 47 tests passing.

- [ ] **Step 4: Commit**

```bash
git add services/api/tests/integration/__init__.py \
        services/api/tests/integration/test_entitlements_e2e.py
git commit -m "test(billing): end-to-end smoke test for entitlements stack"
```

---

## Done. Summary of what shipped

- `tenant_feature_overrides` and `feature_flags` tables (migration `20260506000001`)
- New `entitlements:manage` permission
- `app/billing/features.py` — feature catalog (12 features at launch)
- `app/billing/plans.py` — plan-codename → feature-value mapping (5 plans seeded)
- `app/billing/entitlements.py` — resolver with Redis caching + invalidation
- `app/billing/flags.py` — engineering flag resolver with allowlist/denylist/percent rollout
- `app/billing/deps.py` — `EntitlementsDep` FastAPI dependency
- `app/routers/admin_entitlements.py` — admin CRUD for overrides + flags
- 47 tests covering all of the above

## What this unlocks

- **Every Phase 0 primitive** can ship behind a flag (engineering rollout) AND an entitlement (commercial gate) using:

```python
from app.billing.deps import EntitlementsDep
from app.billing.flags import is_enabled

@router.post("/some/new/feature")
def feature(ents: EntitlementsDep, db: ...):
    ents.require("the_feature")  # 403 if plan doesn't include
    if not is_enabled(db, ents_tenant_id, "the_feature_rollout"):
        raise HTTPException(503, "Feature not yet rolled out")
    ...
```

## Follow-up work (not in this plan)

- Platform-service-side admin UI for editing plan-feature mappings (must precede commercial use of feature gates that need plan-level edits without a code deploy — see memory `platform-side-entitlement-followup.md`)
- Admin web UI for managing overrides + flags (frontend work)
- Sync platform's plan-feature data into `TenantLicenseCache.raw_payload` so `plans.py::resolve_plan_value` can read from the cached payload — at that point delete `PLAN_FEATURES` from `plans.py`

---

*End of plan.*
