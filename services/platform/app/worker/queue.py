from functools import lru_cache

import redis
from rq import Queue

from app.config import settings

QUEUE_NAME = "platform-default"


@lru_cache
def redis_conn() -> redis.Redis:
    return redis.from_url(settings.redis_url)


def task_queue() -> Queue:
    return Queue(QUEUE_NAME, connection=redis_conn())
