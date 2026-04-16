"""Platform periodic tasks.

These are enqueued by the scheduler in __main__.py and executed by the RQ worker.

- check_subscriptions: Enforces trial expiry, grace period → expired transitions
- send_expiry_notifications: Logs notifications for tenants approaching expiry
  (email integration can be added later)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.tables import PlatformTenant, Subscription

logger = logging.getLogger("platform.tasks")


def check_subscriptions() -> str:
    """Scan all active subscriptions and enforce status transitions.

    - trial past trial_ends_at → past_due
    - active past current_period_end → past_due
    - past_due past grace period → expired
    """
    db = SessionLocal()
    try:
        now = datetime.now(UTC)
        transitioned = 0

        # 1) Trials that have expired
        expired_trials = db.execute(
            select(Subscription).where(
                Subscription.status == "trial",
                Subscription.trial_ends_at <= now,
            )
        ).scalars().all()

        for sub in expired_trials:
            sub.status = "past_due"
            sub.updated_at = now
            transitioned += 1
            logger.info("Trial expired → past_due: tenant=%s sub=%s", sub.tenant_id, sub.id)

        # 2) Active subscriptions past their period end
        expired_active = db.execute(
            select(Subscription).where(
                Subscription.status == "active",
                Subscription.current_period_end <= now,
            )
        ).scalars().all()

        for sub in expired_active:
            sub.status = "past_due"
            sub.updated_at = now
            transitioned += 1
            logger.info("Period ended → past_due: tenant=%s sub=%s", sub.tenant_id, sub.id)

        # 3) Past-due subscriptions past grace period → expired
        past_due_subs = db.execute(
            select(Subscription).where(Subscription.status == "past_due")
        ).scalars().all()

        for sub in past_due_subs:
            grace_end = sub.current_period_end + timedelta(days=sub.grace_period_days)
            if now > grace_end:
                sub.status = "expired"
                sub.updated_at = now
                transitioned += 1
                logger.info("Grace period ended → expired: tenant=%s sub=%s", sub.tenant_id, sub.id)

        db.commit()
        msg = f"check_subscriptions: {transitioned} transitions"
        logger.info(msg)
        return msg
    except Exception:
        db.rollback()
        logger.exception("check_subscriptions failed")
        return "error"
    finally:
        db.close()


def send_expiry_notifications() -> str:
    """Identify tenants approaching expiry and log notifications.

    Categories:
    - Trial ending within 3 days
    - Subscription period ending within 7 days
    - Currently in grace period
    - Already expired (reminder to renew)

    In production, these would send emails via the email service.
    For now, they are logged for the platform operator to review.
    """
    db = SessionLocal()
    try:
        now = datetime.now(UTC)
        notifications = []

        # 1) Trials ending soon (within 3 days)
        trial_cutoff = now + timedelta(days=3)
        ending_trials = db.execute(
            select(Subscription, PlatformTenant)
            .join(PlatformTenant, PlatformTenant.id == Subscription.tenant_id)
            .where(
                Subscription.status == "trial",
                Subscription.trial_ends_at <= trial_cutoff,
                Subscription.trial_ends_at > now,
            )
        ).all()

        for sub, tenant in ending_trials:
            days_left = (sub.trial_ends_at - now).days
            notifications.append(f"TRIAL_ENDING: {tenant.name} ({tenant.slug}) — {days_left} day(s) left")

        # 2) Active subscriptions ending within 7 days
        renewal_cutoff = now + timedelta(days=7)
        ending_active = db.execute(
            select(Subscription, PlatformTenant)
            .join(PlatformTenant, PlatformTenant.id == Subscription.tenant_id)
            .where(
                Subscription.status == "active",
                Subscription.current_period_end <= renewal_cutoff,
                Subscription.current_period_end > now,
            )
        ).all()

        for sub, tenant in ending_active:
            days_left = (sub.current_period_end - now).days
            notifications.append(f"RENEWAL_DUE: {tenant.name} ({tenant.slug}) — {days_left} day(s) until renewal")

        # 3) Currently in grace period
        grace_subs = db.execute(
            select(Subscription, PlatformTenant)
            .join(PlatformTenant, PlatformTenant.id == Subscription.tenant_id)
            .where(Subscription.status == "past_due")
        ).all()

        for sub, tenant in grace_subs:
            grace_end = sub.current_period_end + timedelta(days=sub.grace_period_days)
            if now <= grace_end:
                days_left = (grace_end - now).days
                notifications.append(f"GRACE_PERIOD: {tenant.name} ({tenant.slug}) — {days_left} day(s) of grace remaining")

        # 4) Already expired
        expired_subs = db.execute(
            select(Subscription, PlatformTenant)
            .join(PlatformTenant, PlatformTenant.id == Subscription.tenant_id)
            .where(Subscription.status == "expired")
        ).all()

        for sub, tenant in expired_subs:
            notifications.append(f"EXPIRED: {tenant.name} ({tenant.slug}) — subscription expired, needs renewal")

        for n in notifications:
            logger.warning("NOTIFICATION: %s", n)

        msg = f"send_expiry_notifications: {len(notifications)} notifications"
        logger.info(msg)
        return msg
    except Exception:
        logger.exception("send_expiry_notifications failed")
        return "error"
    finally:
        db.close()
