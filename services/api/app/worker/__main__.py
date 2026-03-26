"""RQ worker entrypoint: python -m app.worker"""

from __future__ import annotations

import redis
from rq import Worker

from app.config import settings
from app.worker.queue import QUEUE_NAME


def main() -> None:
    conn = redis.from_url(settings.redis_url)
    worker = Worker([QUEUE_NAME], connection=conn)
    worker.work()


if __name__ == "__main__":
    main()
