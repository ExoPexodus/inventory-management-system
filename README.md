# Inventory management system

Mobile-first, offline-capable inventory and POS platform: **Flutter** cashier + admin apps, **Next.js** admin web, **FastAPI** central API (ledger-based stock), **PostgreSQL** + **Redis**, Dockerized for cloud or on-prem.

## Layout

| Path | Description |
|------|-------------|
| `services/api` | FastAPI backend (SQLAlchemy, Alembic) |
| `packages/sync-protocol` | OpenAPI spec — domain + sync contract |
| `apps/admin-web` | Next.js admin dashboard |
| `apps/cashier` | Cashier Flutter app (`com.inventory.platform`) |
| `apps/admin_mobile` | Admin Flutter app (`com.inventory.platform.admin`) |
| `tools/flutter` | Local Flutter SDK (stable, gitignored from upstream churn — clone with `git clone -b stable --depth 1 https://github.com/flutter/flutter.git tools/flutter`) |

## Quick start (Docker)

1. Copy `.env.example` to `.env` and set secrets.
2. From repo root:

   ```bash
   docker compose up --build
   ```

3. API: `http://localhost:8001` (default host port; set `API_PUBLISH_PORT` in `.env` to change). OpenAPI docs at `/docs`.
4. Set `ADMIN_API_TOKEN` in `.env` (see `.env.example`) for `GET /v1/admin/overview` and enrollment minting. Compose also starts an **RQ worker** (`python -m app.worker`).
5. **Full demo dataset** (destructive — wipes all tenants; keeps operator accounts):  
   `docker compose exec -e IMS_DEMO_RESET_OK=1 api python -m app.scripts.reset_demo_showcase`  
   Prints a fresh cashier **enrollment token** and seeds two shops, products, suppliers, sales history, stock movements, tax overrides, pending/refunded samples, and low-stock SKUs for admin dashboards.
5. Migrations run automatically on container start. To re-run:

   ```bash
   docker compose exec api alembic upgrade head
   ```

## Local API (without Docker for Postgres)

Start Postgres/Redis via Docker, then:

```bash
cd services/api
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
set DATABASE_URL=postgresql+psycopg2://ims:ims_dev_change_me@localhost:5432/ims
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Payment policy (Phase 1)

- **Cash** works offline (queued sync) subject to tenant offline policy tiers.
- **Card** requires **connectivity** by default; the cashier app must block card tender when offline.

## Flutter apps

1. **SDK:** Flutter is expected under `tools/flutter`. If missing:

   ```bash
   git clone --branch stable --depth 1 https://github.com/flutter/flutter.git tools/flutter
   ```

2. **PATH:** Add `tools/flutter/bin` (Windows: full path to repo `tools\flutter\bin`).
3. **Checks:** `cd apps/cashier && flutter analyze && flutter test` (same for `admin_mobile`).
4. **Run without Android SDK:** `flutter run -d windows` or `-d chrome`.
5. **APK / device:** Install Android Studio so `flutter doctor` reports a healthy Android toolchain.

More detail: [`apps/cashier/README.md`](apps/cashier/README.md), [`apps/admin_mobile/README.md`](apps/admin_mobile/README.md).

## Spec

Authoritative HTTP contract: [`packages/sync-protocol/openapi.yaml`](packages/sync-protocol/openapi.yaml).
