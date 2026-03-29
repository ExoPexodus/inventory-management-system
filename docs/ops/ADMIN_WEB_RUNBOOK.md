# Admin web console — stack runbook

## Showcase reset (rich demo data)

Wipes **all tenants** and related rows; **does not** delete `admin_users`.

```bash
docker compose exec -e IMS_DEMO_RESET_OK=1 api python -m app.scripts.reset_demo_showcase
```

Creates tenant `showcase-demo`, two shops, suppliers, tax overrides, ~16 posted sales (cash/card), pending + refunded samples, stock ledger movements, and low-stock items for alerts. Prints a new **enrollment token** for the cashier app.

## Local (hybrid)

1. Start API + DB: from repo root `docker compose up -d postgres redis api worker`
2. Apply migrations and seed operator (set `ADMIN_BOOTSTRAP_EMAIL` / `ADMIN_BOOTSTRAP_PASSWORD` in `services/api` env or compose). For a full demo catalog, run the **Showcase reset** above after operators exist.
3. From `apps/admin-web`: copy `.env.example` → `.env.local`, set `API_INTERNAL_URL=http://localhost:8001` (or published API port).
4. `npm install` && `npm run dev` → http://localhost:3000 — sign in with operator credentials.

## Full stack (Docker)

```bash
docker compose up -d --build
```

- API: `http://localhost:8001` (or `API_PUBLISH_PORT`)
- Admin web: `http://localhost:3000` (or `ADMIN_WEB_PUBLISH_PORT`)
- Operator JWT is stored in an HttpOnly cookie (`ims_operator_jwt`) after POST to Next `/api/auth/login` (server forwards to `/v1/admin/auth/login`).
- Admin-web routes are strictly tenant-scoped by authenticated operator assignment (`admin_users.tenant_id`). Cross-tenant reads/writes are rejected.
- **HTTP + production Node:** If login returns 200 but every page stays on `/login` or API calls fail with 401, the cookie may have been set with `Secure` while you use plain `http://`. Compose sets `COOKIE_SECURE` (default `false`). With HTTPS or a reverse proxy, set `COOKIE_SECURE=true` or ensure `X-Forwarded-Proto: https`.
- Passwords are stored with **bcrypt** (one-way hash), not reversible encryption. Login failures are almost always wrong password, inactive user, or accidental whitespace / quoted `.env` values when seeding.
- If login fails with `Operator is not assigned to a tenant`, run the showcase reset to recreate tenant-scoped demo data and assign operators:
  - `docker compose exec -e IMS_DEMO_RESET_OK=1 api python -m app.scripts.reset_demo_showcase`

## Parity QA (Stitch)

Design references: `docs/stitch/admin-web/` (HTML + `screenshot.webp` per screen). Spot-check each route:

| Route | Stitch folder |
|-------|---------------|
| `/overview` | `executive-overview/` |
| `/orders` | `order-audit-ledger/` |
| `/suppliers` | `supplier-hub/` |
| `/analytics` | `analytics-insights/` |
| `/entries` | `new-entry-hub/` |
| `/inventory` | `inventory-ledger/` |
| `/staff` | `staff-permissions/` |

## Smoke tests

- Login / logout; protected route redirect when cookie cleared.
- Overview KPI load; Orders pagination; Suppliers create; Inventory movements load; Staff role PATCH.
- Supplier list filtering: status + text search should query `/v1/admin/suppliers?status=&q=`.
- Staff filtering: role + email search should query `/v1/admin/operators?role=&q=`.
- `pytest services/api/tests -q` including `test_admin_console_contracts.py`.
