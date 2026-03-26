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
