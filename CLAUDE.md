# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Layout

Monorepo with three runtimes:
- `services/api/` — FastAPI backend (Python 3.12), multi-tenant, ledger-based inventory
- `apps/admin-web/` — Next.js 15 admin dashboard (TypeScript, Tailwind CSS)
- `apps/cashier/` — Flutter offline-first POS app
- `apps/admin_mobile/` — Flutter admin companion app
- `packages/sync-protocol/` — OpenAPI spec (domain contract between backend and cashier)
- `docs/` — Architecture docs and ADRs (read these before large changes)

## Running the Full Stack

```bash
docker compose up --build
# API:       http://localhost:8001  (Swagger: /docs)
# Admin Web: http://localhost:3100
```

Seed demo data (wipes tenant data, keeps operators):
```bash
docker compose exec -e IMS_DEMO_RESET_OK=1 api python -m app.scripts.reset_demo_showcase
```

## Service-Specific Commands

### API (`services/api/`)
```bash
python -m venv .venv && pip install -r requirements.txt
alembic upgrade head          # run migrations
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
python -m app.worker          # RQ background worker
```

Required env vars (copy from `.env.example`): `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `ADMIN_API_TOKEN`.

### Admin Web (`apps/admin-web/`)
```bash
npm install
npm run dev        # port 3000
npm run build
npm run lint
```

### Flutter Apps (`apps/cashier/`, `apps/admin_mobile/`)
```bash
# Flutter SDK is NOT bundled — clone it first:
git clone -b stable --depth 1 https://github.com/flutter/flutter.git tools/flutter

cd apps/cashier   # or apps/admin_mobile
# Flutter SDK is at tools/flutter/bin/flutter (not in PATH):
../../tools/flutter/bin/flutter pub get
../../tools/flutter/bin/flutter analyze
../../tools/flutter/bin/flutter build apk --release   # install with: flutter install
../../tools/flutter/bin/flutter run -d windows        # or -d chrome / -d android
```

### Flutter Android Build — Windows Gotcha

`google_fonts` → `path_provider` → `path_provider_android 2.3.x` pulls in `jni 1.0.0`, which breaks
Gradle on Windows (`jni_flutter:compileReleaseJavaWithJavac` error). Fix with a dependency override
matching the cashier's working version:

```yaml
# in pubspec.yaml
dependency_overrides:
  path_provider_android: "2.2.22"
```

If a new Flutter package causes similar Gradle failures, diff its `pubspec.lock` against
`apps/cashier/pubspec.lock` (known-good baseline) to find the divergent transitive dependency.

## Architecture

### Multi-tenancy & Row-Level Security
Every tenant-scoped table is protected by PostgreSQL RLS. Each request sets session variables (`ims.tenant_id`, `ims.is_admin`) via `app/db/rls.py:set_rls_context()`. Never bypass this — queries that skip the RLS context will leak cross-tenant data.

### Authentication
- **Devices** (cashier/admin mobile): JWT `typ=device`. Enroll at `POST /v1/devices/enroll`, receive access + refresh tokens. Token carries `device_id`, `tenant_id`, `shop_ids`.
- **Operators** (admin web/API): JWT `typ=operator` via `POST /v1/admin/auth/login`, or legacy `X-Admin-Token` header.
- Auth dependencies live in `services/api/app/auth/deps.py` and `app/auth/admin_deps.py`.

### Inventory Ledger
Stock is **never a mutable field** — it is derived from `StockMovements` (immutable ledger rows). Direct stock updates must create movement records, not UPDATE quantities. Adjustments flow through `StockAdjustments` (pending → approved workflow).

### Offline Sync (Cashier ↔ API)
- Pull: `GET /v1/sync/pull` — delta bundle (products, stock snapshots, policies)
- Push: `POST /v1/sync/push` — batch of events (`sale_completed`, `ledger_adjustment`) with idempotency keys
- Conflicts return structured `conflict` objects (e.g. `insufficient_stock`, `card_requires_connectivity`)
- Full protocol in `docs/sync-architecture.md` and `packages/sync-protocol/openapi.yaml`

### Money
All amounts are stored as **integer minor units** (e.g. `unit_price_cents`). Currency metadata (exponent, symbol) is delivered to the cashier via sync pull and formatted client-side. Never store floats for money.

### Background Jobs
Heavy operations (email, analytics aggregation) run via **RQ** backed by Redis. Enqueue via `app/worker.py`; worker process runs separately.

## Database Migrations

```bash
# Create a new migration (auto-generate from model changes)
alembic revision --autogenerate -m "description"
alembic upgrade head
```

Migration files live in `services/api/alembic/versions/`. The API container runs `alembic upgrade head` automatically on start.

## Frontend Patterns

### Currency formatting
`useCurrency()` hook (from `@/lib/currency-context`) provides tenant currency config. Use `formatMoney(cents, currency)` for all money display.
- Each top-level function component in a file needs its own `const currency = useCurrency()` — React context does not scope to child *function declarations*, only to JSX children.
- Server components (`async function`, no `"use client"`) cannot use hooks. Fetch currency server-side: add `serverJsonGet("/v1/admin/tenant-settings/currency")` to the page's `Promise.all` instead.

## Key Docs to Read Before Large Changes

- `docs/architecture.md` — full system design
- `docs/sync-architecture.md` — offline sync, conflict semantics, idempotency
- `docs/client-architecture.md` — cashier state machine, screen flow
- `docs/adr-index.md` — architecture decision records
