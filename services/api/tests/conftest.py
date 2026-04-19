from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models import Tenant


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
