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


def poll_all_tenant_configs() -> dict:
    """Scheduled job: poll platform for every tenant's config. Gated by IMS_PLATFORM_SYNC_MODE."""
    import logging
    from app.config import settings as app_settings

    logger = logging.getLogger(__name__)

    if app_settings.ims_platform_sync_mode != "polling":
        return {"status": "skipped", "reason": f"sync mode is {app_settings.ims_platform_sync_mode}"}

    from app.db.session import SessionLocal
    from app.models import Tenant
    from app.services.platform_sync import poll_tenant_config

    db = SessionLocal()
    applied_count = 0
    failed_count = 0
    total = 0
    try:
        tenants = db.query(Tenant).all()
        total = len(tenants)
        for tenant in tenants:
            try:
                if poll_tenant_config(db, tenant):
                    applied_count += 1
            except Exception as e:
                failed_count += 1
                logger.warning("poll_tenant_config failed for %s: %s", tenant.slug, e)
    finally:
        db.close()

    return {"applied": applied_count, "failed": failed_count, "total": total}
