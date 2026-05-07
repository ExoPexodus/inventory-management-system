# NOTE: `from __future__ import annotations` deliberately absent.

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Tenant


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id, role="owner", role_id=None,
        is_legacy_token=False, permissions=frozenset({"currency:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def _mock_frankfurter(base: str, rates: dict) -> MagicMock:
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = {"base": base, "date": "2026-05-07", "rates": rates}
    m.raise_for_status = MagicMock()
    return m


def test_sync_specific_targets(db, tenant: Tenant, auth_headers) -> None:
    with patch("httpx.get", return_value=_mock_frankfurter("USD", {"INR": 83.5, "EUR": 0.92})):
        resp = TestClient(app).post("/v1/admin/fx-rates/sync", json={
            "base": "USD", "targets": ["INR", "EUR"],
        }, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["base"] == "USD"
    assert body["rates_synced"] == 2
    assert body["rates"]["INR"] == "83.5"
    assert body["rates"]["EUR"] == "0.92"
    assert body["source"] == "frankfurter.app"


def test_sync_empty_targets_fetches_all_supported(db, tenant: Tenant, auth_headers) -> None:
    mock_rates = {"INR": 83.5, "EUR": 0.92, "GBP": 0.79}
    with patch("httpx.get", return_value=_mock_frankfurter("USD", mock_rates)):
        resp = TestClient(app).post("/v1/admin/fx-rates/sync", json={
            "base": "USD", "targets": [],
        }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["rates_synced"] == 3


def test_sync_unsupported_base_returns_400(db, tenant: Tenant, auth_headers) -> None:
    import httpx as httpx_mod
    err = httpx_mod.HTTPStatusError(
        "404", request=MagicMock(), response=MagicMock(status_code=404),
    )
    with patch("httpx.get", side_effect=err):
        resp = TestClient(app).post("/v1/admin/fx-rates/sync", json={
            "base": "XYZ", "targets": ["USD"],
        }, headers=auth_headers)
    assert resp.status_code == 400


def test_sync_network_error_returns_502(db, tenant: Tenant, auth_headers) -> None:
    import httpx as httpx_mod
    with patch("httpx.get", side_effect=httpx_mod.ConnectError("unreachable")):
        resp = TestClient(app).post("/v1/admin/fx-rates/sync", json={
            "base": "USD", "targets": ["EUR"],
        }, headers=auth_headers)
    assert resp.status_code == 502


def test_list_supported_currencies(auth_headers) -> None:
    resp = TestClient(app).get("/v1/admin/fx-rates/supported-currencies", headers=auth_headers)
    assert resp.status_code == 200
    currencies = resp.json()
    assert "USD" in currencies
    assert "INR" in currencies
    assert "EUR" in currencies
    assert currencies == sorted(currencies)
