"""RQ worker entrypoint with built-in scheduler for periodic tasks.

Run with: python -m app.worker

On startup, enqueues periodic tasks (subscription checks, expiry enforcement)
using RQ's scheduler. The worker then processes jobs normally.
"""

from __future__ import annotations

import logging
import threading
import time

import redis
from rq import Worker

from app.config import settings
from app.worker.queue import QUEUE_NAME, task_queue

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s")
logger = logging.getLogger("platform.worker")

# Periodic task intervals (seconds)
SUBSCRIPTION_CHECK_INTERVAL = 3600      # 1 hour
EXPIRY_NOTIFICATION_INTERVAL = 86400    # 24 hours


def _scheduler_loop():
    """Background thread that enqueues periodic tasks at fixed intervals."""
    q = task_queue()
    logger.info("Scheduler started — subscription checks every %ds", SUBSCRIPTION_CHECK_INTERVAL)

    # Stagger the first runs
    time.sleep(30)

    last_sub_check = 0.0
    last_expiry_notify = 0.0

    while True:
        now = time.time()

        if now - last_sub_check >= SUBSCRIPTION_CHECK_INTERVAL:
            try:
                q.enqueue("app.worker.tasks.check_subscriptions")
                logger.info("Enqueued: check_subscriptions")
                last_sub_check = now
            except Exception:
                logger.exception("Failed to enqueue check_subscriptions")

        if now - last_expiry_notify >= EXPIRY_NOTIFICATION_INTERVAL:
            try:
                q.enqueue("app.worker.tasks.send_expiry_notifications")
                logger.info("Enqueued: send_expiry_notifications")
                last_expiry_notify = now
            except Exception:
                logger.exception("Failed to enqueue send_expiry_notifications")

        time.sleep(60)  # check every minute


def main() -> None:
    conn = redis.from_url(settings.redis_url)

    # Start the scheduler in a daemon thread
    scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True)
    scheduler_thread.start()

    # Run the worker
    worker = Worker([QUEUE_NAME], connection=conn)
    worker.work()


if __name__ == "__main__":
    main()
