import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.services.shipping.shiprocket.mapping import map_status, order_to_shiprocket
from app.services.shipping.shiprocket.provider import ShiprocketProvider


def test_map_status_known():
    assert map_status("Delivered") == "delivered"
    assert map_status("In Transit") == "shipped"
    assert map_status("Out For Delivery") == "out_for_delivery"
    assert map_status("Cancelled") == "cancelled"


def test_map_status_unknown_defaults_to_processing():
    assert map_status("some random string xyz") == "processing"


def test_verify_webhook_matching_secret():
    provider = ShiprocketProvider()
    config = {"shiprocket_webhook_secret": "mysecret"}
    assert provider.verify_webhook(b"body", {"x-api-key": "mysecret"}, config) is True


def test_verify_webhook_wrong_secret():
    provider = ShiprocketProvider()
    config = {"shiprocket_webhook_secret": "mysecret"}
    assert provider.verify_webhook(b"body", {"x-api-key": "wrong"}, config) is False


def test_verify_webhook_no_secret_configured():
    provider = ShiprocketProvider()
    assert provider.verify_webhook(b"body", {}, {}) is True


def test_parse_webhook_delivered():
    provider = ShiprocketProvider()
    payload = {
        "awb": "TEST12345",
        "current_status": "Delivered",
        "updated_at": "2026-05-08T10:00:00",
        "location": "Mumbai Hub",
    }
    events = provider.parse_webhook(payload)
    assert len(events) == 1
    ev = events[0]
    assert ev.status == "delivered"
    assert ev.raw_payload["awb"] == "TEST12345"
    assert ev.location == "Mumbai Hub"


def test_parse_webhook_idempotency_key_includes_awb_status_date():
    provider = ShiprocketProvider()
    payload = {
        "awb": "AWB001",
        "current_status": "In Transit",
        "updated_at": "2026-05-08T10:00:00",
    }
    events = provider.parse_webhook(payload)
    assert "AWB001" in events[0].provider_event_id
    assert "In Transit" in events[0].provider_event_id


def test_shiprocket_client_refreshes_token_on_cache_miss():
    mock_redis = MagicMock()
    mock_redis.get.return_value = None
    mock_redis.setex = MagicMock()

    with patch("app.services.shipping.shiprocket.client.redis_conn", return_value=mock_redis), \
         patch("app.services.shipping.shiprocket.client.decrypt_secret", return_value="pass123"), \
         patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        mock_post.return_value.json.return_value = {"token": "fresh_jwt"}
        mock_post.return_value.raise_for_status = MagicMock()

        from app.services.shipping.shiprocket.client import get_token
        token = get_token(uuid.uuid4(), {"shiprocket_email": "test@example.com"})

    assert token == "fresh_jwt"
    mock_redis.setex.assert_called_once()


def test_registry_returns_shiprocket_provider():
    from app.services.shipping.registry import get_provider
    from app.services.shipping.shiprocket.provider import ShiprocketProvider
    provider = get_provider("shiprocket")
    assert isinstance(provider, ShiprocketProvider)


def test_registry_raises_for_unknown_provider():
    from app.services.shipping.registry import get_provider
    from app.services.shipping.base import ShippingNotConfiguredError
    with pytest.raises(ShippingNotConfiguredError):
        get_provider("fedex_doesnt_exist")
