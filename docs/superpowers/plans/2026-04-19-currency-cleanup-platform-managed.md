# Currency Cleanup & Platform-Managed Currency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make tenant operating currency platform-managed — platform is the authoritative editor, api DB caches values locally via HMAC push + poll. Drop the deprecated `display_mode: "convert"` multiplier feature and fix the admin-web cache-staleness bug.

**Architecture:** Platform (`services/platform/`) gains currency + deployment_mode columns on `platform_tenants` and is the editor. API (`services/api/`) receives a push from platform on every change and (for cloud tenants) polls platform periodically as a safety net. API keeps its existing currency columns as a local cache; drops the two convert-mode-specific columns. Admin-web (`apps/admin-web/`) becomes read-only for currency. Platform-web (`apps/platform-web/`) gains a currency editor on the tenant detail page.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL (two separate instances — platform and api have different DBs), RQ/redis (api-side worker), pytest, Next.js 15, TypeScript, Tailwind.

**Reference spec:** [docs/superpowers/specs/2026-04-19-currency-cleanup-platform-managed-design.md](../specs/2026-04-19-currency-cleanup-platform-managed-design.md)

---

## File Structure

### Platform service (`services/platform/`)
- `alembic/versions/{timestamp}_tenant_currency_and_deployment_mode.py` — new migration
- `app/models/tables.py` — `PlatformTenant` updates
- `app/routers/tenants.py` — extend Pydantic bodies, add currency GET/PATCH endpoints
- `app/routers/internal_sync.py` — NEW — `GET /v1/internal/tenants/{slug}/config` endpoint
- `app/services/tenant_config_push.py` — NEW — HMAC push helper
- `app/scripts/backfill_tenant_currency.py` — NEW — cross-DB backfill script
- `app/main.py` — register `internal_sync` router
- `tests/conftest.py` — NEW — fixtures mirroring the api service pattern
- `tests/routers/test_platform_tenant_currency.py` — NEW
- `tests/routers/test_internal_sync.py` — NEW
- `tests/services/test_tenant_config_push.py` — NEW

### API service (`services/api/`)
- `alembic/versions/{timestamp}_drop_convert_mode_add_sync_timestamp.py` — new migration
- `app/models/tables.py` — `Tenant` updates (add `currency_synced_at`, drop two columns)
- `app/routers/admin_platform.py` — currency GET response reshape; PATCH returns 410 Gone
- `app/routers/internal_sync.py` — NEW — `POST /v1/internal/platform-config`
- `app/services/platform_sync.py` — NEW — HMAC pull helper
- `app/worker/tasks.py` — register poll job gated on `IMS_PLATFORM_SYNC_MODE`
- `app/config.py` — add `IMS_PLATFORM_SYNC_MODE`, `IMS_PLATFORM_SYNC_INTERVAL_SECONDS`
- `app/main.py` — register `internal_sync` router
- `tests/routers/test_internal_platform_config.py` — NEW
- `tests/routers/test_admin_platform_currency_cleanup.py` — NEW
- `tests/services/test_platform_sync.py` — NEW

### Admin-web (`apps/admin-web/`)
- `src/lib/currency-context.tsx` — drop deprecated fields, add `refreshCurrency()`, refetch on route change
- `src/lib/format.ts` — remove rate multiplication branch
- `src/app/(main)/settings/page.tsx` — read-only currency section

### Platform-web (`apps/platform-web/`)
- `src/app/(main)/tenants/[id]/page.tsx` — add inline currency editor + deployment_mode selector

---

## Task 1: Platform migration — `platform_tenants` currency + deployment_mode columns

**Files:**
- Create: `services/platform/alembic/versions/{timestamp}_tenant_currency_and_deployment_mode.py`

- [ ] **Step 1: Generate migration file**

```bash
docker compose exec platform alembic revision -m "tenant currency and deployment mode"
```

Alembic will generate a file with a timestamp prefix and revision id. Keep whatever id Alembic produced; replace the body with the content below, setting `down_revision` to the current head in `services/platform/alembic/versions/` (expected: `20260416000001`).

```python
"""tenant currency and deployment mode

Revision ID: <keep alembic's generated value>
Revises: 20260416000001
Create Date: 2026-04-19 ...
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "<keep alembic's value>"
down_revision = "20260416000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "platform_tenants",
        sa.Column("default_currency_code", sa.String(3), nullable=False, server_default="USD"),
    )
    op.add_column(
        "platform_tenants",
        sa.Column("currency_exponent", sa.Integer(), nullable=False, server_default="2"),
    )
    op.add_column(
        "platform_tenants",
        sa.Column("currency_symbol_override", sa.String(8), nullable=True),
    )
    op.add_column(
        "platform_tenants",
        sa.Column("deployment_mode", sa.String(16), nullable=False, server_default="cloud"),
    )


def downgrade() -> None:
    op.drop_column("platform_tenants", "deployment_mode")
    op.drop_column("platform_tenants", "currency_symbol_override")
    op.drop_column("platform_tenants", "currency_exponent")
    op.drop_column("platform_tenants", "default_currency_code")
```

- [ ] **Step 2: Run migration**

```bash
docker compose exec platform alembic upgrade head
```

Expected: clean upgrade, no errors.

- [ ] **Step 3: Verify columns exist**

```bash
docker compose exec platform python -c "from sqlalchemy import create_engine, text; import os; e = create_engine(os.environ['DATABASE_URL']); print(e.connect().execute(text(\"SELECT default_currency_code, deployment_mode FROM platform_tenants LIMIT 1\")).fetchall())"
```

Expected: prints rows with `('USD', 'cloud')` defaults, or `[]` if the platform DB has no tenants yet.

- [ ] **Step 4: Verify round-trip**

```bash
docker compose exec platform alembic downgrade -1 && docker compose exec platform alembic upgrade head
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add services/platform/alembic/versions/
git commit -m "feat(platform): add currency and deployment_mode columns to platform_tenants"
```

---

## Task 2: Update `PlatformTenant` model

**Files:**
- Modify: `services/platform/app/models/tables.py:52-64`

- [ ] **Step 1: Add columns to `PlatformTenant`**

Insert these four columns immediately after `notes` (line 62) and before `created_at`:

```python
    default_currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="USD", server_default="USD")
    currency_exponent: Mapped[int] = mapped_column(Integer, nullable=False, default=2, server_default="2")
    currency_symbol_override: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    deployment_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="cloud", server_default="cloud")
```

Verify `Optional` and `String` / `Integer` are already imported at the top of the file (they are — used by other models).

- [ ] **Step 2: Verify model/migration parity**

```bash
docker compose exec platform alembic check
```

Expected: exit code 0 (no pending autogen diff) for these four columns. Any pre-existing drift on unrelated tables is OK.

- [ ] **Step 3: Commit**

```bash
git add services/platform/app/models/tables.py
git commit -m "feat(platform): add currency and deployment_mode fields to PlatformTenant model"
```

---

## Task 3: Platform test infrastructure (conftest + shop-like fixtures)

**Files:**
- Create: `services/platform/tests/__init__.py` (empty)
- Create: `services/platform/tests/conftest.py`

The platform service has no existing tests today. We need minimal infra before writing tests for subsequent tasks.

- [ ] **Step 1: Install pytest in the platform container**

```bash
docker compose exec platform pip install pytest
```

- [ ] **Step 2: Create `tests/__init__.py`**

Empty file.

- [ ] **Step 3: Create `tests/conftest.py`**

```python
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models import PlatformTenant


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(settings.database_url, pool_pre_ping=True)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine) -> Session:
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def platform_tenant(db: Session) -> PlatformTenant:
    t = PlatformTenant(
        id=uuid.uuid4(),
        name="Test Tenant",
        slug=f"test-{uuid.uuid4().hex[:8]}",
        region="in",
        api_base_url="http://test-api.local",
        api_shared_secret="test-secret-please-replace",
        download_token=uuid.uuid4().hex,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t
```

**Verify `settings.database_url` and `PlatformTenant` import paths** match actual platform layout — inspect `services/platform/app/config.py` and `services/platform/app/models/__init__.py`. Adapt import if needed.

Schema is managed by Alembic migrations (per CLAUDE.md Alembic-only policy) — do NOT add `Base.metadata.create_all(eng)`. The conftest relies on the migrated DB being in place.

- [ ] **Step 4: Verify conftest loads**

```bash
docker compose exec platform python -c "import pytest; from tests.conftest import platform_tenant; print('OK')"
```

Expected: prints `OK`. Any ImportError means fixture imports need adjustment.

- [ ] **Step 5: Commit**

```bash
git add services/platform/tests/
git commit -m "test(platform): add pytest conftest with db and platform_tenant fixtures"
```

---

## Task 4: Platform — currency GET/PATCH endpoints (without push yet)

**Files:**
- Modify: `services/platform/app/routers/tenants.py`
- Create: `services/platform/tests/routers/__init__.py` (empty)
- Create: `services/platform/tests/routers/test_platform_tenant_currency.py`

Push integration comes in Task 6. This task only wires the DB read/write.

- [ ] **Step 1: Write failing tests**

Create `services/platform/tests/routers/__init__.py` (empty), then create `services/platform/tests/routers/test_platform_tenant_currency.py`:

```python
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.auth.deps import OperatorContext
from app.models import PlatformTenant
from app.routers.tenants import (
    PatchTenantCurrencyBody,
    get_tenant_currency,
    patch_tenant_currency,
)


def _ctx():
    return OperatorContext(operator_id=uuid4(), email="op@test.local")


def test_get_currency_returns_platform_values(db: Session, platform_tenant: PlatformTenant) -> None:
    platform_tenant.default_currency_code = "INR"
    platform_tenant.currency_exponent = 2
    platform_tenant.currency_symbol_override = "Rs"
    db.commit()

    result = get_tenant_currency(tenant_id=platform_tenant.id, ctx=_ctx(), db=db)

    assert result.default_currency_code == "INR"
    assert result.currency_exponent == 2
    assert result.currency_symbol_override == "Rs"


def test_patch_currency_updates_all_fields(db: Session, platform_tenant: PlatformTenant) -> None:
    result = patch_tenant_currency(
        tenant_id=platform_tenant.id,
        body=PatchTenantCurrencyBody(
            default_currency_code="INR",
            currency_exponent=2,
            currency_symbol_override="Rs",
        ),
        ctx=_ctx(),
        db=db,
    )
    db.refresh(platform_tenant)

    assert platform_tenant.default_currency_code == "INR"
    assert platform_tenant.currency_exponent == 2
    assert platform_tenant.currency_symbol_override == "Rs"
    # push_status field is set by the Task 6 push integration; for now expect "not_implemented" or similar
    assert result.default_currency_code == "INR"


def test_patch_currency_accepts_partial_update(db: Session, platform_tenant: PlatformTenant) -> None:
    platform_tenant.default_currency_code = "USD"
    platform_tenant.currency_exponent = 2
    db.commit()

    patch_tenant_currency(
        tenant_id=platform_tenant.id,
        body=PatchTenantCurrencyBody(default_currency_code="EUR"),
        ctx=_ctx(),
        db=db,
    )
    db.refresh(platform_tenant)

    assert platform_tenant.default_currency_code == "EUR"
    assert platform_tenant.currency_exponent == 2


def test_patch_rejects_invalid_currency_code() -> None:
    with pytest.raises(Exception):
        PatchTenantCurrencyBody(default_currency_code="TOOLONG")


def test_patch_rejects_negative_exponent() -> None:
    with pytest.raises(Exception):
        PatchTenantCurrencyBody(currency_exponent=-1)
```

**Verify `OperatorContext`** in `services/platform/app/auth/deps.py` — confirm field names (`operator_id`, `email`). Match actual class.

- [ ] **Step 2: Verify failure**

```bash
docker compose exec platform python -m pytest tests/routers/test_platform_tenant_currency.py -v
```

Expected: FAIL — `ImportError: cannot import name 'PatchTenantCurrencyBody'` etc.

- [ ] **Step 3: Add schemas and handlers to `tenants.py`**

Add the following to `services/platform/app/routers/tenants.py`. Place imports alongside existing ones (`Field` from pydantic, `Tenant` already imported as `PlatformTenant`).

Add Pydantic schemas (insert after `TenantListResponse`):

```python
class TenantCurrencyOut(BaseModel):
    default_currency_code: str
    currency_exponent: int
    currency_symbol_override: str | None


class PatchTenantCurrencyBody(BaseModel):
    default_currency_code: str | None = Field(default=None, min_length=3, max_length=3)
    currency_exponent: int | None = Field(default=None, ge=0, le=4)
    currency_symbol_override: str | None = Field(default=None, max_length=8)

    model_config = {"extra": "forbid"}


class TenantCurrencyPatchResult(BaseModel):
    default_currency_code: str
    currency_exponent: int
    currency_symbol_override: str | None
    push_status: str  # "success" | "failed" | "not_implemented"
    push_error: str | None = None
```

Add the two handlers (place after the existing `regenerate_download_token` endpoint):

```python
@router.get("/{tenant_id}/currency", response_model=TenantCurrencyOut)
def get_tenant_currency(
    tenant_id: UUID,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> TenantCurrencyOut:
    tenant = db.get(PlatformTenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return TenantCurrencyOut(
        default_currency_code=tenant.default_currency_code,
        currency_exponent=tenant.currency_exponent,
        currency_symbol_override=tenant.currency_symbol_override,
    )


@router.patch("/{tenant_id}/currency", response_model=TenantCurrencyPatchResult)
def patch_tenant_currency(
    tenant_id: UUID,
    body: PatchTenantCurrencyBody,
    ctx: OperatorDep,
    db: Annotated[Session, Depends(get_db)],
) -> TenantCurrencyPatchResult:
    tenant = db.get(PlatformTenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    sent = body.model_fields_set
    patch_data = body.model_dump(include=sent)
    for field, value in patch_data.items():
        setattr(tenant, field, value)

    write_audit(
        db,
        operator_id=ctx.operator_id,
        action="update_tenant_currency",
        resource_type="tenant",
        resource_id=str(tenant_id),
    )
    db.commit()
    db.refresh(tenant)

    # Push integration added in Task 6
    push_status = "not_implemented"
    push_error = None

    return TenantCurrencyPatchResult(
        default_currency_code=tenant.default_currency_code,
        currency_exponent=tenant.currency_exponent,
        currency_symbol_override=tenant.currency_symbol_override,
        push_status=push_status,
        push_error=push_error,
    )
```

Verify `write_audit` is already imported at the top of the file (line 19 should have it). If not, add it from `app.services.audit_service`.

- [ ] **Step 4: Run tests**

```bash
docker compose exec platform python -m pytest tests/routers/test_platform_tenant_currency.py -v
```

Expected: all 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add services/platform/app/routers/tenants.py services/platform/tests/routers/
git commit -m "feat(platform): add tenant currency GET/PATCH endpoints (push integration pending)"
```

---

## Task 5: Platform — extend tenant create/patch with deployment_mode and currency

**Files:**
- Modify: `services/platform/app/routers/tenants.py` — `TenantCreate`, `TenantPatch`, `TenantOut`, POST and PATCH handlers

- [ ] **Step 1: Write failing test**

Append to `services/platform/tests/routers/test_platform_tenant_currency.py`:

```python
from app.routers.tenants import TenantCreate, TenantPatch, create_tenant, patch_tenant


def test_create_tenant_accepts_currency_and_deployment_mode(db: Session) -> None:
    result = create_tenant(
        body=TenantCreate(
            name="New Tenant",
            slug=f"new-{uuid4().hex[:8]}",
            region="in",
            api_base_url="http://new.local",
            default_currency_code="INR",
            currency_exponent=2,
            currency_symbol_override="Rs",
            deployment_mode="on_prem",
        ),
        ctx=_ctx(),
        db=db,
    )
    # result is a TenantOut; the DB row should have the new fields
    from app.models import PlatformTenant  # local import to avoid unused warning
    tenant = db.get(PlatformTenant, result.id)
    assert tenant.default_currency_code == "INR"
    assert tenant.deployment_mode == "on_prem"


def test_create_tenant_defaults_currency_to_usd_and_mode_to_cloud(db: Session) -> None:
    result = create_tenant(
        body=TenantCreate(
            name="Defaulted",
            slug=f"def-{uuid4().hex[:8]}",
            region="in",
            api_base_url="http://def.local",
        ),
        ctx=_ctx(),
        db=db,
    )
    from app.models import PlatformTenant
    tenant = db.get(PlatformTenant, result.id)
    assert tenant.default_currency_code == "USD"
    assert tenant.currency_exponent == 2
    assert tenant.deployment_mode == "cloud"


def test_patch_tenant_accepts_deployment_mode(db: Session, platform_tenant: PlatformTenant) -> None:
    patch_tenant(
        tenant_id=platform_tenant.id,
        body=TenantPatch(deployment_mode="on_prem"),
        ctx=_ctx(),
        db=db,
    )
    db.refresh(platform_tenant)
    assert platform_tenant.deployment_mode == "on_prem"


def test_patch_tenant_rejects_invalid_deployment_mode() -> None:
    with pytest.raises(Exception):
        TenantPatch(deployment_mode="invalid_mode")
```

- [ ] **Step 2: Verify failure**

```bash
docker compose exec platform python -m pytest tests/routers/test_platform_tenant_currency.py -v
```

Expected: FAIL — `TenantCreate` does not accept the new fields.

- [ ] **Step 3: Extend `TenantCreate`, `TenantPatch`, `TenantOut`**

In `services/platform/app/routers/tenants.py`:

Replace `TenantCreate` (lines 29-34) with:

```python
class TenantCreate(BaseModel):
    name: str
    slug: str
    region: str = "in"
    api_base_url: str
    notes: str | None = None
    default_currency_code: str = Field(default="USD", min_length=3, max_length=3)
    currency_exponent: int = Field(default=2, ge=0, le=4)
    currency_symbol_override: str | None = Field(default=None, max_length=8)
    deployment_mode: str = Field(default="cloud", pattern="^(cloud|on_prem)$")
```

Replace `TenantPatch` (lines 37-41) with:

```python
class TenantPatch(BaseModel):
    name: str | None = None
    region: str | None = None
    api_base_url: str | None = None
    notes: str | None = None
    deployment_mode: str | None = Field(default=None, pattern="^(cloud|on_prem)$")
```

Replace `TenantOut` (lines 44-53) to include the new fields in the response:

```python
class TenantOut(BaseModel):
    id: UUID
    name: str
    slug: str
    region: str
    api_base_url: str
    download_token: str
    notes: str | None
    default_currency_code: str
    currency_exponent: int
    currency_symbol_override: str | None
    deployment_mode: str
    created_at: datetime
    updated_at: datetime
```

Update `_to_out` helper (line 187 onward) to populate the new fields:

```python
def _to_out(t: PlatformTenant) -> TenantOut:
    return TenantOut(
        id=t.id,
        name=t.name,
        slug=t.slug,
        region=t.region,
        api_base_url=t.api_base_url,
        download_token=t.download_token,
        notes=t.notes,
        default_currency_code=t.default_currency_code,
        currency_exponent=t.currency_exponent,
        currency_symbol_override=t.currency_symbol_override,
        deployment_mode=t.deployment_mode,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )
```

Update `create_tenant` handler (lines 102-127) to pass the new fields to the `PlatformTenant(...)` constructor:

```python
    tenant = PlatformTenant(
        name=body.name,
        slug=body.slug,
        region=body.region,
        api_base_url=body.api_base_url,
        api_shared_secret=secrets.token_urlsafe(32),
        download_token=secrets.token_urlsafe(24),
        notes=body.notes,
        default_currency_code=body.default_currency_code,
        currency_exponent=body.currency_exponent,
        currency_symbol_override=body.currency_symbol_override,
        deployment_mode=body.deployment_mode,
    )
```

(The exact constructor body may differ slightly in the existing code; keep all existing fields and append the new four.)

Update `patch_tenant` handler (lines 142-161) — add `deployment_mode` to the `sent = body.model_fields_set` iteration. The existing loop `for field, value in patch_data.items(): setattr(tenant, field, value)` already handles it if the field is in the body.

- [ ] **Step 4: Run tests**

```bash
docker compose exec platform python -m pytest tests/routers/test_platform_tenant_currency.py -v
```

Expected: all 9 PASS (5 original + 4 new).

- [ ] **Step 5: Commit**

```bash
git add services/platform/app/routers/tenants.py services/platform/tests/routers/test_platform_tenant_currency.py
git commit -m "feat(platform): extend tenant create/patch with deployment_mode and currency fields"
```

---

## Task 6: Platform — HMAC push service + wire into PATCH

**Files:**
- Create: `services/platform/app/services/tenant_config_push.py`
- Create: `services/platform/tests/services/__init__.py` (empty)
- Create: `services/platform/tests/services/test_tenant_config_push.py`
- Modify: `services/platform/app/routers/tenants.py` — invoke push from `patch_tenant_currency`

The push signs using the tenant's `api_shared_secret` (per-tenant secret established at provisioning), not the global platform secret. This diverges from the api→platform flow (which uses `settings.jwt_secret`) because the reverse direction needs per-tenant isolation: a compromised secret for one tenant must not allow pushing to others.

- [ ] **Step 1: Write failing tests**

Create `services/platform/tests/services/__init__.py` (empty), then `services/platform/tests/services/test_tenant_config_push.py`:

```python
from __future__ import annotations

import hmac
import hashlib
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session

from app.models import PlatformTenant
from app.services.tenant_config_push import push_tenant_currency_config


def test_push_succeeds_on_2xx(platform_tenant: PlatformTenant) -> None:
    platform_tenant.default_currency_code = "INR"
    platform_tenant.currency_exponent = 2
    platform_tenant.currency_symbol_override = None

    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"applied": True}

    with patch("app.services.tenant_config_push.httpx.post", return_value=mock_resp) as mock_post:
        result = push_tenant_currency_config(platform_tenant)
        assert result.status == "success"
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        # URL should include api_base_url
        assert platform_tenant.api_base_url in mock_post.call_args.args[0]
        # Headers should include HMAC auth + timestamp
        headers = call_kwargs["headers"]
        assert "X-Platform-Auth" in headers
        assert "X-Platform-Timestamp" in headers
        # Body should include tenant_id and currency fields
        body = call_kwargs["json"]
        assert body["tenant_id"] == str(platform_tenant.id)
        assert body["default_currency_code"] == "INR"
        assert body["currency_exponent"] == 2


def test_push_returns_failed_status_on_5xx(platform_tenant: PlatformTenant) -> None:
    mock_resp = Mock()
    mock_resp.status_code = 500
    mock_resp.text = "internal error"

    with patch("app.services.tenant_config_push.httpx.post", return_value=mock_resp):
        result = push_tenant_currency_config(platform_tenant)
        assert result.status == "failed"
        assert "500" in (result.error or "")


def test_push_returns_failed_status_on_timeout(platform_tenant: PlatformTenant) -> None:
    import httpx

    with patch("app.services.tenant_config_push.httpx.post", side_effect=httpx.TimeoutException("timed out")):
        result = push_tenant_currency_config(platform_tenant)
        assert result.status == "failed"
        assert "timeout" in (result.error or "").lower()


def test_push_signs_with_tenant_shared_secret(platform_tenant: PlatformTenant) -> None:
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"applied": True}

    with patch("app.services.tenant_config_push.httpx.post", return_value=mock_resp) as mock_post:
        push_tenant_currency_config(platform_tenant)

        headers = mock_post.call_args.kwargs["headers"]
        timestamp = headers["X-Platform-Timestamp"]
        expected_sig = hmac.new(
            platform_tenant.api_shared_secret.encode("utf-8"),
            f"{timestamp}|{platform_tenant.id}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert headers["X-Platform-Auth"] == expected_sig
```

- [ ] **Step 2: Verify failure**

```bash
docker compose exec platform python -m pytest tests/services/test_tenant_config_push.py -v
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the service**

Create `services/platform/app/services/tenant_config_push.py`:

```python
"""Push tenant configuration to api service via HMAC-signed HTTP call."""
from __future__ import annotations

import hmac
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from app.models import PlatformTenant

PUSH_TIMEOUT_SECONDS = 10


@dataclass
class PushResult:
    status: str  # "success" | "failed"
    error: str | None = None
    applied: bool | None = None


def push_tenant_currency_config(tenant: PlatformTenant) -> PushResult:
    """POST currency config to the tenant's api_base_url. Single attempt, no retry."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    signing_input = f"{timestamp}|{tenant.id}".encode("utf-8")
    signature = hmac.new(
        tenant.api_shared_secret.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).hexdigest()

    url = f"{tenant.api_base_url.rstrip('/')}/v1/internal/platform-config"
    body = {
        "tenant_id": str(tenant.id),
        "default_currency_code": tenant.default_currency_code,
        "currency_exponent": tenant.currency_exponent,
        "currency_symbol_override": tenant.currency_symbol_override,
        "synced_at": timestamp,
    }
    headers = {
        "X-Platform-Auth": signature,
        "X-Platform-Timestamp": timestamp,
        "Content-Type": "application/json",
    }

    try:
        resp = httpx.post(url, json=body, headers=headers, timeout=PUSH_TIMEOUT_SECONDS)
    except httpx.TimeoutException:
        return PushResult(status="failed", error="push request timeout")
    except httpx.HTTPError as e:
        return PushResult(status="failed", error=f"http error: {e}")

    if not (200 <= resp.status_code < 300):
        return PushResult(status="failed", error=f"{resp.status_code}: {resp.text[:200]}")

    try:
        body = resp.json()
        applied = body.get("applied")
    except Exception:
        applied = None

    return PushResult(status="success", applied=applied)
```

- [ ] **Step 4: Wire push into `patch_tenant_currency`**

In `services/platform/app/routers/tenants.py`, update `patch_tenant_currency` (added in Task 4). Replace the `# Push integration added in Task 6` block with:

```python
    from app.services.tenant_config_push import push_tenant_currency_config
    push = push_tenant_currency_config(tenant)
    push_status = push.status
    push_error = push.error
```

(Import at top of file is fine too — put `from app.services.tenant_config_push import push_tenant_currency_config` alongside other imports.)

- [ ] **Step 5: Run tests**

```bash
docker compose exec platform python -m pytest tests/services/test_tenant_config_push.py tests/routers/test_platform_tenant_currency.py -v
```

Expected: all PASS. The earlier test `test_patch_currency_updates_all_fields` will now see `push_status` as either "success" or "failed" depending on whether the test environment can reach any URL (likely "failed" since `http://test-api.local` doesn't resolve). That's fine — update the assertion there:

```python
    # push was attempted; status is either success or failed
    assert result.push_status in ("success", "failed")
```

(Make this edit to the test file.)

- [ ] **Step 6: Commit**

```bash
git add services/platform/app/services/tenant_config_push.py services/platform/app/routers/tenants.py services/platform/tests/services/
git commit -m "feat(platform): HMAC push currency config to api on tenant update"
```

---

## Task 7: Platform — internal pull endpoint

**Files:**
- Create: `services/platform/app/routers/internal_sync.py`
- Create: `services/platform/tests/routers/test_internal_sync.py`
- Modify: `services/platform/app/main.py` — register router

- [ ] **Step 1: Write failing tests**

Create `services/platform/tests/routers/test_internal_sync.py`:

```python
from __future__ import annotations

import hmac
import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models import PlatformTenant
from app.routers.internal_sync import get_tenant_config_internal


def _hmac_headers(tenant: PlatformTenant) -> dict:
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    sig = hmac.new(
        tenant.api_shared_secret.encode("utf-8"),
        f"{timestamp}|{tenant.slug}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {"X-Platform-Auth": sig, "X-Platform-Timestamp": timestamp}


def test_get_config_returns_currency_with_valid_hmac(
    db: Session, platform_tenant: PlatformTenant,
) -> None:
    platform_tenant.default_currency_code = "INR"
    platform_tenant.currency_exponent = 2
    db.commit()

    headers = _hmac_headers(platform_tenant)
    from fastapi import Request

    # We call the handler directly; Request object with headers is needed for HMAC check.
    # Use a mock Request.
    from unittest.mock import Mock
    request = Mock()
    request.headers = {
        "X-Platform-Auth": headers["X-Platform-Auth"],
        "X-Platform-Timestamp": headers["X-Platform-Timestamp"],
    }

    result = get_tenant_config_internal(slug=platform_tenant.slug, request=request, db=db)
    assert result.default_currency_code == "INR"
    assert result.currency_exponent == 2


def test_get_config_rejects_missing_hmac(db: Session, platform_tenant: PlatformTenant) -> None:
    from unittest.mock import Mock
    from fastapi import HTTPException
    request = Mock()
    request.headers = {}

    with pytest.raises(HTTPException) as exc:
        get_tenant_config_internal(slug=platform_tenant.slug, request=request, db=db)
    assert exc.value.status_code == 401


def test_get_config_rejects_invalid_hmac(db: Session, platform_tenant: PlatformTenant) -> None:
    from unittest.mock import Mock
    from fastapi import HTTPException
    request = Mock()
    request.headers = {
        "X-Platform-Auth": "deadbeef",
        "X-Platform-Timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    with pytest.raises(HTTPException) as exc:
        get_tenant_config_internal(slug=platform_tenant.slug, request=request, db=db)
    assert exc.value.status_code == 401


def test_get_config_rejects_stale_timestamp(db: Session, platform_tenant: PlatformTenant) -> None:
    from unittest.mock import Mock
    from fastapi import HTTPException

    stale_ts = "2020-01-01T00:00:00Z"
    sig = hmac.new(
        platform_tenant.api_shared_secret.encode("utf-8"),
        f"{stale_ts}|{platform_tenant.slug}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    request = Mock()
    request.headers = {"X-Platform-Auth": sig, "X-Platform-Timestamp": stale_ts}

    with pytest.raises(HTTPException) as exc:
        get_tenant_config_internal(slug=platform_tenant.slug, request=request, db=db)
    assert exc.value.status_code == 401


def test_get_config_404_for_unknown_slug(db: Session, platform_tenant: PlatformTenant) -> None:
    from unittest.mock import Mock
    from fastapi import HTTPException
    headers = _hmac_headers(platform_tenant)
    request = Mock()
    request.headers = {
        "X-Platform-Auth": headers["X-Platform-Auth"],
        "X-Platform-Timestamp": headers["X-Platform-Timestamp"],
    }

    with pytest.raises(HTTPException) as exc:
        get_tenant_config_internal(slug="does-not-exist", request=request, db=db)
    # Either 401 (HMAC doesn't match unknown slug) or 404 (if we check existence first)
    assert exc.value.status_code in (401, 404)
```

- [ ] **Step 2: Verify failure**

```bash
docker compose exec platform python -m pytest tests/routers/test_internal_sync.py -v
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement the router**

Create `services/platform/app/routers/internal_sync.py`:

```python
"""Internal sync endpoints for api→platform pull (HMAC-authenticated)."""
from __future__ import annotations

import hmac
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import PlatformTenant

router = APIRouter(prefix="/v1/internal", tags=["Internal Sync"])

HMAC_SKEW_SECONDS = 300  # 5 minutes allowed drift


def _verify_tenant_hmac(request: Request, tenant: PlatformTenant, slug: str) -> None:
    signature = request.headers.get("X-Platform-Auth")
    timestamp = request.headers.get("X-Platform-Timestamp")
    if not signature or not timestamp:
        raise HTTPException(status_code=401, detail="Missing HMAC headers")

    try:
        ts_dt = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid timestamp format")

    if abs((datetime.now(UTC) - ts_dt).total_seconds()) > HMAC_SKEW_SECONDS:
        raise HTTPException(status_code=401, detail="Stale timestamp")

    expected = hmac.new(
        tenant.api_shared_secret.encode("utf-8"),
        f"{timestamp}|{slug}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")


class TenantConfigOut(BaseModel):
    default_currency_code: str
    currency_exponent: int
    currency_symbol_override: str | None
    synced_at: str


@router.get("/tenants/{slug}/config", response_model=TenantConfigOut)
def get_tenant_config_internal(
    slug: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> TenantConfigOut:
    tenant = db.execute(
        select(PlatformTenant).where(PlatformTenant.slug == slug)
    ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=401, detail="Unknown tenant or invalid signature")

    _verify_tenant_hmac(request, tenant, slug)

    synced_at = tenant.updated_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    return TenantConfigOut(
        default_currency_code=tenant.default_currency_code,
        currency_exponent=tenant.currency_exponent,
        currency_symbol_override=tenant.currency_symbol_override,
        synced_at=synced_at,
    )
```

**Security note:** unknown slug returns the same 401 as invalid signature to avoid leaking tenant existence.

- [ ] **Step 4: Register the router**

In `services/platform/app/main.py`, find the existing `app.include_router(...)` calls. Add:

```python
from app.routers import internal_sync
# ...
app.include_router(internal_sync.router)
```

- [ ] **Step 5: Run tests**

```bash
docker compose exec platform python -m pytest tests/routers/test_internal_sync.py -v
```

Expected: all 5 PASS.

- [ ] **Step 6: Commit**

```bash
git add services/platform/app/routers/internal_sync.py services/platform/app/main.py services/platform/tests/routers/test_internal_sync.py
git commit -m "feat(platform): add internal HMAC-authenticated tenant config pull endpoint"
```

---

## Task 8: API — remove convert-mode code paths

**Files:**
- Modify: `services/api/app/routers/admin_platform.py` — `CurrencySettingsOut` drop fields, `PATCH /tenant-settings/currency` → 410 Gone

This task removes all api-side code that references `currency_display_mode` and `currency_conversion_rate`, clearing the way for Tasks 8 and 9 to drop the columns.

- [ ] **Step 1: Write failing tests**

Create `services/api/tests/routers/test_admin_platform_currency_cleanup.py`:

```python
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminContext
from app.models import Tenant
from app.routers.admin_platform import (
    get_currency_settings,
    patch_currency_settings,
)


def _ctx(tenant_id):
    return AdminContext(
        user_id=None,
        tenant_id=tenant_id,
        role="admin",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset(),
    )


def test_get_currency_response_has_no_display_mode_or_conversion_rate(
    db: Session, tenant: Tenant,
) -> None:
    tenant.default_currency_code = "INR"
    tenant.currency_exponent = 2
    db.commit()

    result = get_currency_settings(ctx=_ctx(tenant.id), db=db)
    result_dict = result.model_dump()

    assert "display_mode" not in result_dict
    assert "conversion_rate" not in result_dict
    assert result_dict["currency_code"] == "INR"


def test_patch_currency_returns_410_gone(db: Session, tenant: Tenant) -> None:
    # The endpoint still exists but raises 410 Gone
    from app.routers.admin_platform import PatchCurrencyBody

    with pytest.raises(HTTPException) as exc:
        patch_currency_settings(
            body=PatchCurrencyBody(currency_code="USD"),
            ctx=_ctx(tenant.id),
            db=db,
        )
    assert exc.value.status_code == 410
    assert "platform" in exc.value.detail.lower()
```

- [ ] **Step 2: Verify failure**

```bash
docker compose exec api python -m pytest tests/routers/test_admin_platform_currency_cleanup.py -v
```

Expected: FAIL — current GET includes `display_mode`/`conversion_rate`; current PATCH doesn't raise.

- [ ] **Step 3: Update `admin_platform.py`**

In `services/api/app/routers/admin_platform.py`:

**3a.** Update `CurrencySettingsOut` (around lines 45-51). Remove `display_mode` and `conversion_rate` fields if present. Final shape:

```python
class CurrencySettingsOut(BaseModel):
    currency_code: str
    currency_symbol: str
    currency_exponent: int
    supported_currencies: list[SupportedCurrency]  # whatever existing shape
```

**3b.** Update `get_currency_settings` (around lines 60-84). Remove any references to `tenant.currency_display_mode` and `tenant.currency_conversion_rate`. Keep `default_currency_code`, `currency_exponent`, `currency_symbol_override` (→ `currency_symbol`).

**3c.** Update `PatchCurrencyBody` (around lines 87-ish). Strip `display_mode` and `conversion_rate` fields. Keep only `currency_code`, `currency_exponent`, `currency_symbol_override`.

**3d.** Replace the body of `patch_currency_settings` entirely with:

```python
@router.patch(
    "/tenant-settings/currency",
    response_model=CurrencySettingsOut,
    dependencies=[require_permission("settings:write")],
)
def patch_currency_settings(
    body: PatchCurrencyBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> CurrencySettingsOut:
    raise HTTPException(
        status_code=410,
        detail="Currency is now managed by your platform administrator. Contact support to change.",
    )
```

The endpoint still exists (so existing clients get a clear error instead of 404), but it no longer mutates anything.

- [ ] **Step 4: Run tests**

```bash
docker compose exec api python -m pytest tests/routers/test_admin_platform_currency_cleanup.py -v
docker compose exec api python -m pytest tests/ -v 2>&1 | tail -20
```

Expected: the 2 new tests PASS. Pre-existing failures from Employee→User merge remain the same count (no new regressions).

- [ ] **Step 5: Commit**

```bash
git add services/api/app/routers/admin_platform.py services/api/tests/routers/test_admin_platform_currency_cleanup.py
git commit -m "feat(api): remove convert-mode fields from currency response; return 410 on PATCH"
```

---

## Task 9: API — migration to drop convert-mode columns, add `currency_synced_at`

**Files:**
- Create: `services/api/alembic/versions/{timestamp}_platform_managed_currency.py`

- [ ] **Step 1: Generate migration**

```bash
docker compose exec api alembic revision -m "platform managed currency"
```

Replace generated file body with:

```python
"""platform managed currency

Revision ID: <keep alembic's value>
Revises: 20260419120000
Create Date: 2026-04-19 ...
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "<keep alembic's value>"
down_revision = "20260419120000"  # reconciliation auto-resolve migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("currency_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_column("tenants", "currency_conversion_rate")
    op.drop_column("tenants", "currency_display_mode")


def downgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("currency_display_mode", sa.String(16), nullable=False, server_default="symbol"),
    )
    op.add_column(
        "tenants",
        sa.Column("currency_conversion_rate", sa.Float(), nullable=True),
    )
    op.drop_column("tenants", "currency_synced_at")
```

**Verify `down_revision`** — open the latest file in `services/api/alembic/versions/` (from prior merged work, the latest is `20260419120000_auto_resolve_reconciliation.py`).

- [ ] **Step 2: Run migration**

```bash
docker compose exec api alembic upgrade head
```

Expected: clean.

- [ ] **Step 3: Verify column dropped**

```bash
docker compose exec api python -c "from sqlalchemy import create_engine, text; import os; e = create_engine(os.environ['DATABASE_URL']); cols = [r[0] for r in e.connect().execute(text(\"SELECT column_name FROM information_schema.columns WHERE table_name='tenants'\")).fetchall()]; print('currency_synced_at' in cols, 'currency_display_mode' not in cols, 'currency_conversion_rate' not in cols)"
```

Expected: `True True True`.

- [ ] **Step 4: Round-trip**

```bash
docker compose exec api alembic downgrade -1 && docker compose exec api alembic upgrade head
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add services/api/alembic/versions/
git commit -m "feat(api): drop convert-mode columns and add currency_synced_at on tenants"
```

---

## Task 10: API — update `Tenant` model to match migration

**Files:**
- Modify: `services/api/app/models/tables.py:110-135`

- [ ] **Step 1: Edit `Tenant` model**

In `services/api/app/models/tables.py`:

- **Remove** the `currency_display_mode` column (line 119).
- **Remove** the `currency_conversion_rate` column (line 120).
- **Add** after `currency_symbol_override` (line 118):

```python
    currency_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 2: Verify parity**

```bash
docker compose exec api alembic check
```

Expected: no diff for these three columns.

- [ ] **Step 3: Run tests to confirm nothing in the existing codebase still references the dropped fields**

```bash
docker compose exec api python -m pytest tests/ 2>&1 | tail -20
```

Expected: no new errors/failures vs. baseline.

If anything errors with `AttributeError: 'Tenant' object has no attribute 'currency_display_mode'`, grep for remaining references and remove them (should have been handled by Task 10 but this catches misses).

- [ ] **Step 4: Commit**

```bash
git add services/api/app/models/tables.py
git commit -m "feat(api): update Tenant model — drop convert-mode fields, add currency_synced_at"
```

---

## Task 11: API — internal receive-push endpoint

**Files:**
- Create: `services/api/app/routers/internal_sync.py`
- Create: `services/api/tests/routers/test_internal_platform_config.py`
- Modify: `services/api/app/main.py` — register router
- Modify: `services/api/app/config.py` — add `platform_api_secret` if not present (it exists already per exploration, confirm)

- [ ] **Step 1: Confirm shared secret config**

Inspect `services/api/app/config.py`. The field `platform_api_secret` should exist (from prior license-sync work). If not, add:

```python
    platform_api_secret: str = ""  # HMAC shared secret for platform↔api sync
```

**IMPORTANT correction to spec:** the push direction uses `api_shared_secret` which lives in platform DB per tenant. For the api to verify incoming pushes, it needs the SAME secret per tenant. Two options:

- **(a)** api stores a copy of `api_shared_secret` in its own `tenants` table (new column). Platform pushes both provision this at tenant creation.
- **(b)** api uses a single global shared secret (`platform_api_secret` env var) for all tenants. Simpler. Matches the existing license-sync flow direction.

The existing license-sync uses option (b) — single secret shared across all tenants. For consistency, we use **option (b)** here too. Platform's push signs using `settings.jwt_secret` (same secret used by `_verify_hmac` in api→platform direction). API verifies using its `platform_api_secret` env var. Both must be configured to the same value at deployment time.

**Revise Task 6:** the push should sign with `settings.jwt_secret` (platform-side setting, which happens to be the shared HMAC secret). NOT `tenant.api_shared_secret`. Similarly, the pull (Task 7) should sign with the same global secret. This means per-tenant isolation is not achieved at the HMAC layer; it comes from the `tenant_id` in the signed payload.

**Before implementing Task 11, update Task 6 and Task 7:**

Revisit `services/platform/app/services/tenant_config_push.py` — change the signing line from `tenant.api_shared_secret` to `settings.jwt_secret` (import `from app.config import settings`). Also update tests to assert against the global secret.

Revisit `services/platform/app/routers/internal_sync.py` `_verify_tenant_hmac` — change the verification from `tenant.api_shared_secret` to `settings.jwt_secret`. Also update tests.

Once those are revised, proceed with Task 11 below.

- [ ] **Step 2: Write failing tests for api's receive endpoint**

Create `services/api/tests/routers/test_internal_platform_config.py`:

```python
from __future__ import annotations

import hmac
import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Tenant
from app.routers.internal_sync import (
    PlatformConfigPayload,
    apply_platform_config,
    verify_push_hmac,
)


def _sign(body: dict) -> tuple[dict, str]:
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    sig = hmac.new(
        settings.platform_api_secret.encode("utf-8"),
        f"{timestamp}|{body['tenant_id']}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {"X-Platform-Auth": sig, "X-Platform-Timestamp": timestamp}, timestamp


def test_apply_newer_config_updates_tenant_and_returns_applied(
    db: Session, tenant: Tenant,
) -> None:
    payload = PlatformConfigPayload(
        tenant_id=tenant.id,
        default_currency_code="INR",
        currency_exponent=2,
        currency_symbol_override="Rs",
        synced_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    result = apply_platform_config(db, payload)
    db.refresh(tenant)

    assert result["applied"] is True
    assert tenant.default_currency_code == "INR"
    assert tenant.currency_exponent == 2
    assert tenant.currency_symbol_override == "Rs"
    assert tenant.currency_synced_at is not None


def test_apply_older_config_is_noop(db: Session, tenant: Tenant) -> None:
    # Start with a recent sync
    tenant.default_currency_code = "USD"
    tenant.currency_synced_at = datetime.now(UTC)
    db.commit()

    older_ts = "2020-01-01T00:00:00Z"
    payload = PlatformConfigPayload(
        tenant_id=tenant.id,
        default_currency_code="INR",
        currency_exponent=2,
        currency_symbol_override=None,
        synced_at=older_ts,
    )
    result = apply_platform_config(db, payload)
    db.refresh(tenant)

    assert result["applied"] is False
    assert tenant.default_currency_code == "USD"  # unchanged


def test_verify_hmac_accepts_valid_signature(tenant: Tenant) -> None:
    body = {"tenant_id": str(tenant.id)}
    headers, ts = _sign(body)
    verify_push_hmac(
        signature=headers["X-Platform-Auth"],
        timestamp=headers["X-Platform-Timestamp"],
        tenant_id=str(tenant.id),
    )


def test_verify_hmac_rejects_invalid_signature(tenant: Tenant) -> None:
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        verify_push_hmac(
            signature="deadbeef",
            timestamp=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            tenant_id=str(tenant.id),
        )
    assert exc.value.status_code == 401


def test_apply_404_for_unknown_tenant(db: Session) -> None:
    from fastapi import HTTPException
    payload = PlatformConfigPayload(
        tenant_id=uuid4(),
        default_currency_code="INR",
        currency_exponent=2,
        currency_symbol_override=None,
        synced_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    with pytest.raises(HTTPException) as exc:
        apply_platform_config(db, payload)
    assert exc.value.status_code == 404
```

- [ ] **Step 3: Verify failure**

```bash
docker compose exec api python -m pytest tests/routers/test_internal_platform_config.py -v
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 4: Implement the router**

Create `services/api/app/routers/internal_sync.py`:

```python
"""Internal sync endpoints for receiving pushes from the platform service."""
from __future__ import annotations

import hmac
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.models import Tenant

router = APIRouter(prefix="/v1/internal", tags=["Internal Sync"])

HMAC_SKEW_SECONDS = 300
CLOCK_SKEW_TOLERANCE_SECONDS = 2


class PlatformConfigPayload(BaseModel):
    tenant_id: UUID
    default_currency_code: str
    currency_exponent: int
    currency_symbol_override: str | None
    synced_at: str


def verify_push_hmac(signature: str | None, timestamp: str | None, tenant_id: str) -> None:
    if not signature or not timestamp:
        raise HTTPException(status_code=401, detail="Missing HMAC headers")
    try:
        ts_dt = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid timestamp format")
    if abs((datetime.now(UTC) - ts_dt).total_seconds()) > HMAC_SKEW_SECONDS:
        raise HTTPException(status_code=401, detail="Stale timestamp")

    expected = hmac.new(
        settings.platform_api_secret.encode("utf-8"),
        f"{timestamp}|{tenant_id}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")


def apply_platform_config(db: Session, payload: PlatformConfigPayload) -> dict:
    """Apply a config push if the synced_at is newer than the stored value."""
    tenant = db.get(Tenant, payload.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    payload_ts = datetime.strptime(payload.synced_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    if tenant.currency_synced_at is not None:
        delta = (payload_ts - tenant.currency_synced_at).total_seconds()
        if delta <= CLOCK_SKEW_TOLERANCE_SECONDS:
            return {"applied": False, "reason": "payload not newer"}

    tenant.default_currency_code = payload.default_currency_code
    tenant.currency_exponent = payload.currency_exponent
    tenant.currency_symbol_override = payload.currency_symbol_override
    tenant.currency_synced_at = payload_ts
    db.commit()
    return {"applied": True}


@router.post("/platform-config")
def receive_platform_config(
    payload: PlatformConfigPayload,
    db: Annotated[Session, Depends(get_db)],
    x_platform_auth: Annotated[str | None, Header()] = None,
    x_platform_timestamp: Annotated[str | None, Header()] = None,
) -> dict:
    verify_push_hmac(x_platform_auth, x_platform_timestamp, str(payload.tenant_id))
    return apply_platform_config(db, payload)
```

- [ ] **Step 5: Register the router**

In `services/api/app/main.py`, add alongside existing router includes:

```python
from app.routers import internal_sync
# ...
app.include_router(internal_sync.router)
```

- [ ] **Step 6: Run tests**

```bash
docker compose exec api python -m pytest tests/routers/test_internal_platform_config.py -v
```

Expected: all 5 PASS.

- [ ] **Step 7: Commit**

```bash
git add services/api/app/routers/internal_sync.py services/api/app/main.py services/api/tests/routers/test_internal_platform_config.py
git commit -m "feat(api): HMAC-authenticated endpoint to receive platform config pushes"
```

---

## Task 12: API — platform sync service + poll worker job

**Files:**
- Create: `services/api/app/services/platform_sync.py`
- Create: `services/api/tests/services/test_platform_sync.py`
- Modify: `services/api/app/worker/tasks.py`
- Modify: `services/api/app/config.py` — add `IMS_PLATFORM_SYNC_MODE` and `IMS_PLATFORM_SYNC_INTERVAL_SECONDS`

- [ ] **Step 1: Add config fields**

In `services/api/app/config.py`:

```python
    ims_platform_sync_mode: str = "polling"  # "polling" | "offline"
    ims_platform_sync_interval_seconds: int = 300
    platform_base_url: str = "http://platform:8000"  # if not already set
```

Verify these don't already exist (they might — inspect file).

- [ ] **Step 2: Write failing test**

Create `services/api/tests/services/test_platform_sync.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session

from app.models import Tenant
from app.services.platform_sync import poll_tenant_config


def test_poll_updates_tenant_on_newer_platform_config(
    db: Session, tenant: Tenant,
) -> None:
    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "default_currency_code": "INR",
        "currency_exponent": 2,
        "currency_symbol_override": None,
        "synced_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    with patch("app.services.platform_sync.httpx.get", return_value=mock_resp):
        applied = poll_tenant_config(db, tenant)

    db.refresh(tenant)
    assert applied is True
    assert tenant.default_currency_code == "INR"
    assert tenant.currency_synced_at is not None


def test_poll_skips_when_platform_returns_older_config(
    db: Session, tenant: Tenant,
) -> None:
    tenant.default_currency_code = "USD"
    tenant.currency_synced_at = datetime.now(UTC)
    db.commit()

    mock_resp = Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "default_currency_code": "INR",
        "currency_exponent": 2,
        "currency_symbol_override": None,
        "synced_at": "2020-01-01T00:00:00Z",
    }

    with patch("app.services.platform_sync.httpx.get", return_value=mock_resp):
        applied = poll_tenant_config(db, tenant)

    db.refresh(tenant)
    assert applied is False
    assert tenant.default_currency_code == "USD"


def test_poll_logs_and_returns_false_on_platform_error(
    db: Session, tenant: Tenant,
) -> None:
    import httpx

    with patch(
        "app.services.platform_sync.httpx.get",
        side_effect=httpx.HTTPError("platform down"),
    ):
        applied = poll_tenant_config(db, tenant)

    db.refresh(tenant)
    assert applied is False
    # Tenant currency unchanged
```

- [ ] **Step 3: Verify failure**

```bash
docker compose exec api python -m pytest tests/services/test_platform_sync.py -v
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 4: Implement the service**

Create `services/api/app/services/platform_sync.py`:

```python
"""Poll platform service for authoritative tenant config."""
from __future__ import annotations

import hmac
import hashlib
import logging
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Tenant
from app.routers.internal_sync import PlatformConfigPayload, apply_platform_config

logger = logging.getLogger(__name__)

POLL_TIMEOUT_SECONDS = 10


def poll_tenant_config(db: Session, tenant: Tenant) -> bool:
    """Fetch current config from platform and apply if newer. Returns True if applied."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    signing_input = f"{timestamp}|{tenant.slug}".encode("utf-8")
    signature = hmac.new(
        settings.platform_api_secret.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).hexdigest()

    url = f"{settings.platform_base_url.rstrip('/')}/v1/internal/tenants/{tenant.slug}/config"
    headers = {
        "X-Platform-Auth": signature,
        "X-Platform-Timestamp": timestamp,
    }

    try:
        resp = httpx.get(url, headers=headers, timeout=POLL_TIMEOUT_SECONDS)
    except httpx.HTTPError as e:
        logger.warning("platform_sync poll failed for tenant %s: %s", tenant.slug, e)
        return False

    if not (200 <= resp.status_code < 300):
        logger.warning(
            "platform_sync poll non-2xx for tenant %s: %s %s",
            tenant.slug, resp.status_code, resp.text[:200],
        )
        return False

    body = resp.json()
    payload = PlatformConfigPayload(
        tenant_id=tenant.id,
        default_currency_code=body["default_currency_code"],
        currency_exponent=body["currency_exponent"],
        currency_symbol_override=body.get("currency_symbol_override"),
        synced_at=body["synced_at"],
    )
    result = apply_platform_config(db, payload)
    return result.get("applied", False)
```

- [ ] **Step 5: Register the poll job**

In `services/api/app/worker/tasks.py`, add a new task function at the bottom:

```python
def poll_all_tenant_configs() -> dict:
    """Scheduled job: poll platform for every tenant's config. Gated by IMS_PLATFORM_SYNC_MODE."""
    from app.config import settings as app_settings
    if app_settings.ims_platform_sync_mode != "polling":
        return {"status": "skipped", "reason": "sync mode offline"}

    from app.db.session import SessionLocal
    from app.models import Tenant
    from app.services.platform_sync import poll_tenant_config

    db = SessionLocal()
    applied_count = 0
    failed_count = 0
    try:
        tenants = db.query(Tenant).all()
        for tenant in tenants:
            try:
                if poll_tenant_config(db, tenant):
                    applied_count += 1
            except Exception as e:
                failed_count += 1
                logger.warning("poll_tenant_config failed for %s: %s", tenant.slug, e)
    finally:
        db.close()

    return {"applied": applied_count, "failed": failed_count, "total": len(tenants)}
```

**Add scheduling:** the existing worker likely has a scheduler registration point. Inspect `services/api/app/worker/` for any `schedule.py` or similar. If the project uses `rq-scheduler`, register the job there with cron interval `*/5 * * * *` (every 5 minutes). If no scheduler exists, document the pattern to invoke this manually via `rq enqueue app.worker.tasks.poll_all_tenant_configs` or via a separate cron.

For this plan, the simplest approach is to provide the function and document deployment will wire it up via infrastructure (cron, k8s CronJob, rq-scheduler, etc.). That keeps this task testable without depending on scheduler specifics.

- [ ] **Step 6: Run tests**

```bash
docker compose exec api python -m pytest tests/services/test_platform_sync.py -v
```

Expected: all 3 PASS.

- [ ] **Step 7: Commit**

```bash
git add services/api/app/services/platform_sync.py services/api/app/worker/tasks.py services/api/app/config.py services/api/tests/services/test_platform_sync.py
git commit -m "feat(api): platform sync poll service gated on IMS_PLATFORM_SYNC_MODE"
```

---

## Task 13: Cross-DB backfill script

**Files:**
- Create: `services/platform/app/scripts/backfill_tenant_currency.py`

This is a one-time script, not an Alembic migration, because it reads from the api DB and writes to the platform DB.

- [ ] **Step 1: Create the script**

```python
"""One-time backfill: copy currency fields from api.tenants into platform_tenants.

Usage:
    PLATFORM_DATABASE_URL=... API_DATABASE_URL=... python -m app.scripts.backfill_tenant_currency
"""
from __future__ import annotations

import logging
import os
import sys

from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> int:
    platform_url = os.environ.get("PLATFORM_DATABASE_URL")
    api_url = os.environ.get("API_DATABASE_URL")
    if not platform_url or not api_url:
        logger.error("Both PLATFORM_DATABASE_URL and API_DATABASE_URL must be set")
        return 1

    platform_engine = create_engine(platform_url)
    api_engine = create_engine(api_url)

    # Read api tenants
    with api_engine.connect() as api_conn:
        api_rows = api_conn.execute(text(
            "SELECT slug, default_currency_code, currency_exponent, currency_symbol_override FROM tenants"
        )).fetchall()
    logger.info("Found %d api.tenants rows", len(api_rows))

    api_by_slug = {r[0]: r for r in api_rows}

    # Update platform tenants
    with platform_engine.begin() as plat_conn:
        plat_rows = plat_conn.execute(text(
            "SELECT id, slug FROM platform_tenants"
        )).fetchall()
        logger.info("Found %d platform_tenants rows", len(plat_rows))

        updated = 0
        skipped = 0
        for (plat_id, slug) in plat_rows:
            api_row = api_by_slug.get(slug)
            if api_row is None:
                logger.warning("platform_tenant slug=%s has no matching api.tenants row; skipping", slug)
                skipped += 1
                continue
            plat_conn.execute(text(
                """
                UPDATE platform_tenants
                SET default_currency_code = :code,
                    currency_exponent = :exp,
                    currency_symbol_override = :sym
                WHERE id = :id
                """
            ), {
                "code": api_row[1],
                "exp": api_row[2],
                "sym": api_row[3],
                "id": plat_id,
            })
            updated += 1

    logger.info("Backfill complete: updated=%d, skipped=%d", updated, skipped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Dry-run the backfill**

```bash
docker compose exec platform python -c "
import os
os.environ['PLATFORM_DATABASE_URL'] = os.environ['DATABASE_URL']  # platform's own DB
os.environ['API_DATABASE_URL'] = 'postgresql://ims:ims@postgres:5432/ims'  # api DB
from app.scripts.backfill_tenant_currency import main
main()
"
```

(Adapt the API_DATABASE_URL to match your docker-compose setup — check `services/api` DATABASE_URL.)

Expected: log output saying "updated=N, skipped=M".

- [ ] **Step 3: Verify via a spot-check**

```bash
docker compose exec platform python -c "from sqlalchemy import create_engine, text; import os; e = create_engine(os.environ['DATABASE_URL']); print(e.connect().execute(text('SELECT slug, default_currency_code FROM platform_tenants LIMIT 5')).fetchall())"
```

Expected: currencies reflect what api had.

- [ ] **Step 4: Commit**

```bash
git add services/platform/app/scripts/backfill_tenant_currency.py
git commit -m "feat(platform): cross-DB backfill script for tenant currency from api to platform"
```

---

## Task 14: Admin-web — currency context + format cleanup

**Files:**
- Modify: `apps/admin-web/src/lib/currency-context.tsx`
- Modify: `apps/admin-web/src/lib/format.ts`

- [ ] **Step 1: Update `currency-context.tsx`**

Open `apps/admin-web/src/lib/currency-context.tsx`. Replace the provider implementation (lines 22-42) with:

```tsx
"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { usePathname } from "next/navigation";

export type CurrencyConfig = {
  code: string;
  exponent: number;
  symbol: string;
  symbolOverride: string | null;
};

const DEFAULT_CONFIG: CurrencyConfig = {
  code: "USD",
  exponent: 2,
  symbol: "$",
  symbolOverride: null,
};

type CurrencyContextValue = {
  currency: CurrencyConfig;
  refreshCurrency: () => Promise<void>;
};

const CurrencyContext = createContext<CurrencyContextValue>({
  currency: DEFAULT_CONFIG,
  refreshCurrency: async () => {},
});

export function CurrencyProvider({ children }: { children: React.ReactNode }) {
  const [currency, setCurrency] = useState<CurrencyConfig>(DEFAULT_CONFIG);
  const pathname = usePathname();

  const refreshCurrency = useCallback(async () => {
    try {
      const r = await fetch("/api/ims/v1/admin/tenant-settings/currency");
      if (!r.ok) return;
      const data = await r.json();
      setCurrency({
        code: data.currency_code,
        exponent: data.currency_exponent,
        symbol: data.currency_symbol,
        symbolOverride: data.currency_symbol_override ?? null,
      });
    } catch {
      // Network failures leave current values in place; monitoring catches repeated failures.
    }
  }, []);

  // Initial fetch
  useEffect(() => {
    void refreshCurrency();
  }, [refreshCurrency]);

  // Refetch on route change (fixes stale-after-platform-change bug)
  useEffect(() => {
    void refreshCurrency();
  }, [pathname, refreshCurrency]);

  return (
    <CurrencyContext.Provider value={{ currency, refreshCurrency }}>
      {children}
    </CurrencyContext.Provider>
  );
}

export function useCurrency(): CurrencyConfig {
  return useContext(CurrencyContext).currency;
}

export function useRefreshCurrency(): () => Promise<void> {
  return useContext(CurrencyContext).refreshCurrency;
}
```

**Important:** the exported `CurrencyConfig` type no longer has `displayMode` or `conversionRate`. Any consumer using those fields will break the TypeScript build — which is intentional; Task 15 fixes `format.ts` and the settings page.

- [ ] **Step 2: Update `format.ts`**

Open `apps/admin-web/src/lib/format.ts`. Replace the `formatMoney` function (lines 13-22) with:

```typescript
export function formatMoney(cents: number, currency: CurrencyConfig): string {
  const major = cents / Math.pow(10, currency.exponent);
  const symbol = currency.symbolOverride ?? currency.symbol;
  return `${symbol}${major.toFixed(currency.exponent)}`;
}
```

Remove any remaining references to `displayMode` or `conversionRate` elsewhere in the file.

- [ ] **Step 3: Build to catch regressions**

```bash
cd apps/admin-web && npm run build
```

Expected: if any consumer still references dropped fields, the build fails with a TypeScript error pointing to the file+line. Fix each one by removing the reference. Common hits: the settings page (handled in Task 15).

If build fails only on `settings/page.tsx`, that's expected — Task 15 addresses it.

- [ ] **Step 4: Commit**

```bash
git add apps/admin-web/src/lib/currency-context.tsx apps/admin-web/src/lib/format.ts
git commit -m "feat(admin-web): remove convert-mode from currency context; refetch on route change"
```

---

## Task 15: Admin-web — read-only currency section

**Files:**
- Modify: `apps/admin-web/src/app/(main)/settings/page.tsx:415-481`

- [ ] **Step 1: Replace the currency section**

In `apps/admin-web/src/app/(main)/settings/page.tsx`, find the currency section (lines 415-481). Replace the entire section with:

```tsx
<section className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
  <h2 className="text-lg font-semibold text-slate-900">Currency</h2>
  <p className="mt-1 text-sm text-slate-600">
    Your tenant's currency is managed by your platform administrator. To request a change, please contact support.
  </p>
  <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Code</dt>
      <dd className="mt-1 text-sm font-semibold text-slate-900">{currency.code}</dd>
    </div>
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Symbol</dt>
      <dd className="mt-1 text-sm font-semibold text-slate-900">
        {currency.symbolOverride ?? currency.symbol}
      </dd>
    </div>
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">Exponent</dt>
      <dd className="mt-1 text-sm font-semibold text-slate-900">{currency.exponent}</dd>
    </div>
  </dl>
</section>
```

Ensure `currency` is sourced from `useCurrency()` higher up in the component (it likely already is).

Remove all currency-related state hooks that were tied to editing: `currencyCode`, `setCurrencyCode`, `displayMode`, `conversionRate`, `saveCurrency()`, etc. — grep the file for `currency` and remove anything no longer needed after this section is read-only.

- [ ] **Step 2: Build**

```bash
cd apps/admin-web && npm run build 2>&1 | tail -20
```

Expected: clean build.

- [ ] **Step 3: Lint**

```bash
npm run lint 2>&1 | tail -10
```

Expected: no new errors. Pre-existing warnings OK.

- [ ] **Step 4: Commit**

```bash
git add apps/admin-web/src/app/\(main\)/settings/page.tsx
git commit -m "feat(admin-web): make currency section read-only (platform-managed)"
```

---

## Task 16: Platform-web — tenant currency editor

**Files:**
- Modify: `apps/platform-web/src/app/(main)/tenants/[id]/page.tsx`

The platform-web tenant detail page currently has no edit form. Adding the currency section inline (rather than a separate edit page) keeps scope small.

- [ ] **Step 1: Inspect the existing tenant detail page**

Read `apps/platform-web/src/app/(main)/tenants/[id]/page.tsx` fully. Identify:
- How the tenant is fetched (the `GET /v1/platform/tenants/{id}` response).
- Existing section structure / primitives used.
- Whether the page is `"use client"` or a server component.

- [ ] **Step 2: Add Currency section**

Add a new section on the tenant detail page (place after the notes/metadata section, before the subscription section if there is one):

```tsx
// Add to the top of the file if not present:
import { useCallback, useEffect, useState } from "react";

// Inside the tenant detail component:
type CurrencyForm = {
  default_currency_code: string;
  currency_exponent: number;
  currency_symbol_override: string | null;
};

const SUPPORTED = [
  { code: "USD", exponent: 2 },
  { code: "INR", exponent: 2 },
  { code: "IDR", exponent: 0 },
  { code: "EUR", exponent: 2 },
  { code: "GBP", exponent: 2 },
];

function CurrencySection({ tenantId }: { tenantId: string }) {
  const [form, setForm] = useState<CurrencyForm | null>(null);
  const [saving, setSaving] = useState(false);
  const [pushStatus, setPushStatus] = useState<string | null>(null);
  const [pushError, setPushError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const r = await fetch(`/api/platform/v1/platform/tenants/${tenantId}/currency`);
    if (!r.ok) return;
    const data = await r.json();
    setForm(data);
  }, [tenantId]);

  useEffect(() => { void load(); }, [load]);

  const save = async () => {
    if (!form) return;
    setSaving(true);
    setPushError(null);
    const r = await fetch(`/api/platform/v1/platform/tenants/${tenantId}/currency`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });
    setSaving(false);
    if (!r.ok) {
      setPushError(`HTTP ${r.status}`);
      return;
    }
    const data = await r.json();
    setPushStatus(data.push_status);
    if (data.push_error) setPushError(data.push_error);
  };

  if (!form) return <div className="text-sm text-slate-500">Loading…</div>;

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-lg font-semibold">Currency</h2>
      <p className="mt-1 text-sm text-slate-600">
        Operating currency for this tenant. Changes are pushed to the tenant's api instance on save.
      </p>
      <div className="mt-4 grid gap-4 sm:grid-cols-3">
        <label>
          <span className="text-sm font-medium text-slate-700">Code</span>
          <select
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            value={form.default_currency_code}
            onChange={(e) => {
              const picked = SUPPORTED.find((c) => c.code === e.target.value);
              setForm({ ...form, default_currency_code: e.target.value, currency_exponent: picked?.exponent ?? 2 });
            }}
          >
            {SUPPORTED.map((c) => (
              <option key={c.code} value={c.code}>{c.code}</option>
            ))}
          </select>
        </label>
        <label>
          <span className="text-sm font-medium text-slate-700">Exponent</span>
          <input
            type="number"
            readOnly
            className="mt-1 block w-full rounded-md border border-slate-300 bg-slate-50 px-3 py-2 text-sm"
            value={form.currency_exponent}
          />
        </label>
        <label>
          <span className="text-sm font-medium text-slate-700">Symbol override (optional)</span>
          <input
            type="text"
            maxLength={8}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            value={form.currency_symbol_override ?? ""}
            onChange={(e) => setForm({ ...form, currency_symbol_override: e.target.value || null })}
          />
        </label>
      </div>
      {pushStatus && (
        <p className={`mt-3 text-sm ${pushStatus === "success" ? "text-green-600" : "text-red-600"}`}>
          {pushStatus === "success" ? "Pushed to tenant api." : "Push failed."}
          {pushError && <span className="ml-1">({pushError})</span>}
        </p>
      )}
      <div className="mt-4">
        <button
          onClick={save}
          disabled={saving}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </section>
  );
}
```

Place `<CurrencySection tenantId={tenant.id} />` inside the main JSX of the detail page, alongside other sections.

**Adapt** the component to match the existing design-system primitives if platform-web uses the same `@/components/ui/primitives` library as admin-web. The above uses raw Tailwind for portability.

- [ ] **Step 3: Add deployment_mode dropdown**

Add a smaller section for `deployment_mode` (cloud / on_prem) using the existing tenant-detail data. Tenant detail likely already shows the tenant's metadata; add the dropdown here:

```tsx
// Inside tenant detail JSX near existing tenant metadata:
<label className="block">
  <span className="text-sm font-medium text-slate-700">Deployment mode</span>
  <select
    value={tenant.deployment_mode}
    onChange={async (e) => {
      if (!confirm("Changing deployment_mode requires matching IMS_PLATFORM_SYNC_MODE env var on the api instance. Continue?")) return;
      await fetch(`/api/platform/v1/platform/tenants/${tenant.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deployment_mode: e.target.value }),
      });
      location.reload();
    }}
    className="mt-1 block rounded-md border border-slate-300 px-3 py-2 text-sm"
  >
    <option value="cloud">Cloud</option>
    <option value="on_prem">On-prem</option>
  </select>
</label>
```

- [ ] **Step 4: Build and lint**

```bash
cd apps/platform-web && npm run build && npm run lint 2>&1 | tail -15
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add apps/platform-web/src/app/\(main\)/tenants/
git commit -m "feat(platform-web): tenant currency editor and deployment_mode selector"
```

---

## Task 17: End-to-end verification

**Files:** none — manual verification.

- [ ] **Step 1: Run full backend test suites**

```bash
docker compose exec api python -m pytest tests/ 2>&1 | tail -10
docker compose exec platform python -m pytest tests/ 2>&1 | tail -10
```

Expected: api shows prior baseline failures (8 pre-existing from operator_id issue) + all new tests pass. Platform shows all new tests pass (no prior baseline).

- [ ] **Step 2: Start full stack**

```bash
docker compose up
```

Wait for platform (8002), api (8001 or 8200), admin-web (3100), platform-web (3200) to all be reachable.

- [ ] **Step 3: Happy path — cloud tenant**

1. Use platform-web to navigate to a test tenant's detail page.
2. In Currency section, change currency to INR. Save. Verify "Pushed to tenant api." message.
3. Open admin-web for that tenant. Navigate to Settings. Verify Currency section shows INR read-only.
4. Change currency in platform-web again (USD). Save. Verify admin-web next navigation shows USD.

- [ ] **Step 4: Cache-stale fix verification**

1. In admin-web, stay on one page (don't navigate).
2. In platform-web, change currency to EUR. Save.
3. In admin-web, navigate to another route (e.g. /overview → /shops). Verify currency updates on navigation without a full page reload.

- [ ] **Step 5: Poll safety net**

1. Set `IMS_PLATFORM_SYNC_MODE=polling` and `IMS_PLATFORM_SYNC_INTERVAL_SECONDS=60` on api (short interval for testing).
2. Simulate a failed push: stop the api instance, change currency in platform-web, restart api.
3. Wait 60 seconds. Verify api picks up the new currency via poll.

- [ ] **Step 6: On-prem mode**

1. Set `IMS_PLATFORM_SYNC_MODE=offline` on api and restart it.
2. Change currency in platform-web. Verify platform still attempts push (works normally).
3. Verify api's poll job does not run (no outbound GET to platform — confirm via logs).

- [ ] **Step 7: Convert-mode removal**

1. Query admin-web `/api/ims/v1/admin/tenant-settings/currency`. Verify response has no `display_mode` or `conversion_rate` keys.
2. Attempt `PATCH /api/ims/v1/admin/tenant-settings/currency`. Verify 410 Gone.

- [ ] **Step 8: Historical-data sanity**

1. Find a tenant with historical transactions.
2. Change currency to a different code.
3. Verify all historical receipts still display their original cent amounts (no retroactive conversion).

---

## Completion

After Task 17 passes, the feature is shippable.

**Deployment order** (critical — the api migration drops columns):

1. Deploy admin-web (read-only currency + context refetch + format.ts cleanup) first.
2. Deploy api (code removes convert-mode references; new internal-sync endpoints; worker poll job).
3. Run api Alembic migration (drops columns).
4. Deploy platform (new endpoints; tenant create/patch extensions; push service).
5. Run platform Alembic migration.
6. Run cross-DB backfill script.
7. Deploy platform-web (new currency editor + deployment_mode selector).
8. Set `IMS_PLATFORM_SYNC_MODE` env var on api instances (polling for cloud, offline for on-prem).

**Out of scope (future specs):**
- Platform-web tenant create UI form.
- Migration of additional tenant settings to platform (license date, plan flags, etc.).
- Background retry queue for failed pushes.
- Per-tenant HMAC secrets (currently uses global `platform_api_secret`).
