# Inventory API (FastAPI)

Modular monolith: device enrollment, sync pull/push, ledger-based stock.

## Run locally

```bash
python -m venv .venv
# Windows: .\.venv\Scripts\activate
pip install -r requirements.txt
set DATABASE_URL=postgresql+psycopg2://ims:ims_dev_change_me@localhost:5432/ims
alembic upgrade head
python -m app.scripts.seed_demo
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Docs (Docker default host port): http://localhost:8001/docs  
- Enroll device: `POST /v1/devices/enroll` with `enrollment_token` from `seed_demo` or `POST /v1/admin/enrollment-tokens`.
- Refresh: `POST /v1/devices/refresh` with `refresh_token`.
- Sync: `GET /v1/sync/pull?shop_id=...` and `POST /v1/sync/push` with `Authorization: Bearer <access_token>`.
- Admin (requires `ADMIN_API_TOKEN` + header `X-Admin-Token`): `GET /v1/admin/overview`, `POST /v1/admin/enrollment-tokens`, `POST /v1/admin/jobs/ping`.

## Worker (RQ)

```bash
python -m app.worker
```

Uses `REDIS_URL` and queue `ims-default`.

## Docker

From repo root: `docker compose up --build`. Migrations run on API container start; compose also starts the RQ worker.
