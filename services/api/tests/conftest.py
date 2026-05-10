from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models import Shop, Tenant


@pytest.fixture(autouse=True)
def _reset_storefront_rate_limit():
    """Wipe storefront rate-limit Redis keys before each test.

    Without this, the storefront rate-limiter (which uses real Redis even in
    tests) accumulates the per-IP request counter across the whole pytest
    run. With ~30 storefront tests each making several requests from
    127.0.0.1, the 120/min window is breached and later tests get 429s
    instead of their expected responses.
    """
    try:
        import redis as sync_redis
        client = sync_redis.from_url(settings.redis_url, decode_responses=True)
        for key in client.scan_iter(match="rl:storefront:*"):
            client.delete(key)
        client.close()
    except Exception:
        # Redis unavailable — non-storefront tests don't care; storefront
        # tests will fail-open via the middleware's existing fallback.
        pass
    yield


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(settings.database_url, pool_pre_ping=True)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine) -> Session:
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def tenant(db: Session) -> Tenant:
    t = Tenant(
        id=uuid.uuid4(),
        name="Test Tenant",
        slug=f"test-{uuid.uuid4().hex[:8]}",
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@pytest.fixture()
def shop(db: Session, tenant: Tenant) -> Shop:
    s = Shop(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name=f"Test Shop {uuid.uuid4().hex[:6]}",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s
