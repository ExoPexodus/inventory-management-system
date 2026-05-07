from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.models import FxRate, Tenant
from app.services.fx_sync_service import sync_rates


def _mock_response(base: str, rates: dict) -> MagicMock:
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = {"base": base, "date": "2026-05-07", "rates": rates}
    m.raise_for_status = MagicMock()
    return m


def test_sync_rates_upserts_correctly(db, tenant: Tenant) -> None:
    mock_resp = _mock_response("USD", {"INR": 83.5, "EUR": 0.92})
    with patch("httpx.get", return_value=mock_resp):
        result = sync_rates(db, tenant.id, "USD", ["INR", "EUR"])

    assert result == {"INR": "83.5", "EUR": "0.92"}

    rows = db.query(FxRate).filter_by(tenant_id=tenant.id).all()
    assert len(rows) == 2
    pair = {(r.from_currency, r.to_currency): Decimal(r.rate) for r in rows}
    assert pair[("USD", "INR")] == Decimal("83.5")
    assert pair[("USD", "EUR")] == Decimal("0.92")
    assert all(r.source == "frankfurter" for r in rows)


def test_sync_rates_updates_existing(db, tenant: Tenant) -> None:
    with patch("httpx.get", return_value=_mock_response("USD", {"INR": 83.0})):
        sync_rates(db, tenant.id, "USD", ["INR"])

    with patch("httpx.get", return_value=_mock_response("USD", {"INR": 84.2})):
        sync_rates(db, tenant.id, "USD", ["INR"])

    rows = db.query(FxRate).filter_by(tenant_id=tenant.id, from_currency="USD", to_currency="INR").all()
    assert len(rows) == 1
    assert Decimal(rows[0].rate) == Decimal("84.2")


def test_sync_rates_skips_same_base(db, tenant: Tenant) -> None:
    with patch("httpx.get") as mock_get:
        result = sync_rates(db, tenant.id, "USD", ["USD"])
    mock_get.assert_not_called()
    assert result == {}


def test_sync_rates_skips_unsupported_currencies(db, tenant: Tenant) -> None:
    mock_resp = _mock_response("USD", {"EUR": 0.92})
    with patch("httpx.get", return_value=mock_resp) as mock_get:
        result = sync_rates(db, tenant.id, "USD", ["EUR", "XYZ"])

    call_params = mock_get.call_args.kwargs.get("params", {})
    assert "XYZ" not in call_params.get("to", "")
    assert "EUR" in result
