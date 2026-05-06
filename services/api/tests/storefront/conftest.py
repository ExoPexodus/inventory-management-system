import pytest

from app.db.session import get_db
from app.main import app


@pytest.fixture(autouse=True)
def _override_storefront_db(db):
    app.dependency_overrides[get_db] = lambda: db
    yield
    app.dependency_overrides.pop(get_db, None)
