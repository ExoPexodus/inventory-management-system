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


def sweep_expired_reservations() -> str:
    """Scheduled job: mark all past-expiry active reservations as 'expired'.

    Safe to call on any cadence. Recommended schedule: every 1-5 minutes via cron
    or rq-scheduler. Operators can also enqueue it on demand via the admin
    endpoint POST /v1/admin/reservations/sweep-expired (Task 5).

    Sets is_admin=True in the RLS context so the sweep can see rows across all
    tenants without requiring a per-tenant session variable.
    """
    import logging

    from app.db.rls import set_rls_context
    from app.db.session import SessionLocal
    from app.services.reservation_service import sweep_expired

    logger = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        set_rls_context(db, is_admin=True, tenant_id=None)
        count = sweep_expired(db)
        db.commit()
        logger.info("Reservation sweep complete: %d expired", count)
        return f"swept {count} reservations"
    except Exception:
        logger.exception("Reservation sweep failed")
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


def deliver_webhook(delivery_log_id: str) -> str:
    """RQ task: attempt delivery of one webhook event. Called by the worker process."""
    from app.services.webhook_service import deliver_webhook_sync
    return deliver_webhook_sync(delivery_log_id)


def dispatch_shipment(order_id: str) -> str:
    """RQ task: dispatch one order to its configured shipping provider.

    Called automatically on order.confirmed if the channel has a
    shipping_provider in config. Also callable manually via admin API.
    """
    import logging
    from app.db.rls import set_rls_context
    from app.db.session import SessionLocal
    from app.models import Order

    logger = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        set_rls_context(db, is_admin=True, tenant_id=None)
        order = db.get(Order, order_id)
        if order is None:
            return f"order {order_id} not found"
        if order.fulfillment_status not in ("pending", "failed"):
            return f"order already in status {order.fulfillment_status!r}, skipping"
        from app.services.shipping.dispatcher import dispatch_order
        success = dispatch_order(db, order)
        return "dispatched" if success else "skipped_or_failed"
    except Exception:
        logger.exception("dispatch_shipment failed for order %s", order_id)
        return "error"
    finally:
        db.close()


def sweep_abandoned_carts(idle_hours: int = 2) -> str:
    """RQ task: find carts idle for idle_hours and send recovery emails.

    A cart is eligible if:
    - It has a pending CheckoutSession with a customer_email
    - The CartItem was last updated more than idle_hours ago
    """
    import logging
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from app.db.rls import set_rls_context
    from app.db.session import SessionLocal
    from app.models import CartItem, CheckoutSession
    from app.services.email_service import send_abandoned_cart_email

    logger = logging.getLogger(__name__)
    db = SessionLocal()
    sent_count = 0
    try:
        set_rls_context(db, is_admin=True, tenant_id=None)
        cutoff = datetime.now(UTC) - timedelta(hours=idle_hours)
        rows = db.execute(
            select(
                CartItem.cart_token,
                CartItem.tenant_id,
                CartItem.channel_id,
                CheckoutSession.customer_email,
            )
            .join(
                CheckoutSession,
                (CheckoutSession.cart_token == CartItem.cart_token) &
                (CheckoutSession.status == "pending"),
            )
            .where(
                CartItem.updated_at < cutoff,
                CheckoutSession.customer_email.isnot(None),
            )
            .distinct()
        ).all()

        for cart_token, tenant_id, channel_id, customer_email in rows:
            if not customer_email:
                continue
            try:
                ok = send_abandoned_cart_email(
                    db=db,
                    tenant_id=tenant_id,
                    channel_id=channel_id,
                    cart_token=cart_token,
                    customer_email=customer_email,
                )
                if ok:
                    sent_count += 1
            except Exception:
                logger.warning("Failed abandoned cart email for token %s", cart_token, exc_info=True)

        return f"sent {sent_count} abandoned cart emails"
    except Exception:
        logger.exception("sweep_abandoned_carts failed")
        return "error"
    finally:
        db.close()
