"""RQ task callables (importable by name for enqueue)."""

from datetime import UTC, datetime


def ping() -> str:
    return "pong"


def aggregate_report_placeholder(tenant_id: str) -> str:
    """Writes a heartbeat marker in Redis (real side effect for worker smoke tests)."""
    from app.worker.queue import redis_conn

    r = redis_conn()
    key = f"ims:tenant:{tenant_id}:last_report_job_utc"
    r.set(key, datetime.now(UTC).isoformat(), ex=86400 * 7)
    return "ok"


def sync_all_tenant_licenses() -> str:
    """Pull license state from platform service for every tenant and cache locally."""
    import logging

    from app.db.session import SessionLocal
    from app.services.license_service import sync_all_tenant_licenses as _sync_all

    logger = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        count = _sync_all(db)
        logger.info("License sync complete: %d tenants synced", count)
        return f"synced {count} tenants"
    except Exception:
        logger.exception("License sync failed")
        return "error"
    finally:
        db.close()
