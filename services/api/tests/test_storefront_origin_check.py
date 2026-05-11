"""Tests for the per-channel CORS Origin allowlist middleware."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.testclient import TestClient
from starlette.types import ASGIApp

from app.middleware.storefront_origin_check import (
    STOREFRONT_PREFIX,
    StorefrontOriginCheckMiddleware,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_channel_mock(allowed_origins: list[str] | None = None) -> MagicMock:
    ch = MagicMock()
    ch.config = {}
    if allowed_origins is not None:
        ch.config["allowed_origins"] = allowed_origins
    return ch


def _make_request(path: str, origin: str | None = None, channel_id: str | None = None) -> Request:
    """Build a minimal Starlette Request for testing middleware dispatch."""
    headers: list[tuple[bytes, bytes]] = [
        (b"host", b"testserver"),
    ]
    if origin:
        headers.append((b"origin", origin.encode()))
    if channel_id:
        headers.append((b"x-channel-id", channel_id.encode()))

    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": headers,
    }
    return Request(scope)


async def _ok_call_next(request: Request) -> Response:
    return Response("OK", status_code=200)


_FAKE_CHANNEL_ID = "00000000-0000-0000-0000-000000000001"


def _build_middleware() -> StorefrontOriginCheckMiddleware:
    """Build the middleware with a dummy app (we test dispatch directly)."""
    dummy_app: ASGIApp = AsyncMock()
    return StorefrontOriginCheckMiddleware(dummy_app)


def _db_mock_for(channel) -> MagicMock:
    db = MagicMock()
    db.get = MagicMock(return_value=channel)
    db.close = MagicMock()
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_no_origin_header_passes_through() -> None:
    """Server-to-server requests (no Origin) always pass without hitting DB."""
    mw = _build_middleware()
    request = _make_request(
        f"{STOREFRONT_PREFIX}/products",
        origin=None,
        channel_id=_FAKE_CHANNEL_ID,
    )
    with patch("app.db.session.SessionLocal") as mock_session:
        response = await mw.dispatch(request, _ok_call_next)
    assert response.status_code == 200
    # No DB call needed when there's no Origin
    mock_session.assert_not_called()


@pytest.mark.anyio
async def test_origin_in_allowlist_passes() -> None:
    """A matching Origin is accepted and response gets ACAO header."""
    ch = _make_channel_mock(allowed_origins=["https://stickerize.com"])
    mw = _build_middleware()
    request = _make_request(
        f"{STOREFRONT_PREFIX}/products",
        origin="https://stickerize.com",
        channel_id=_FAKE_CHANNEL_ID,
    )
    with patch("app.db.session.SessionLocal", return_value=_db_mock_for(ch)):
        response = await mw.dispatch(request, _ok_call_next)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://stickerize.com"


@pytest.mark.anyio
async def test_origin_not_in_allowlist_rejected() -> None:
    """An Origin not in allowed_origins gets 403."""
    ch = _make_channel_mock(allowed_origins=["https://stickerize.com"])
    mw = _build_middleware()
    request = _make_request(
        f"{STOREFRONT_PREFIX}/products",
        origin="https://evil.com",
        channel_id=_FAKE_CHANNEL_ID,
    )
    with patch("app.db.session.SessionLocal", return_value=_db_mock_for(ch)):
        response = await mw.dispatch(request, _ok_call_next)
    assert response.status_code == 403
    import json
    assert json.loads(response.body)["detail"] == "Origin not allowed for this channel"


@pytest.mark.anyio
async def test_empty_allowlist_passes_all_origins() -> None:
    """When allowed_origins is empty, all origins are permitted."""
    ch = _make_channel_mock(allowed_origins=[])
    mw = _build_middleware()
    request = _make_request(
        f"{STOREFRONT_PREFIX}/products",
        origin="https://anybody.com",
        channel_id=_FAKE_CHANNEL_ID,
    )
    with patch("app.db.session.SessionLocal", return_value=_db_mock_for(ch)):
        response = await mw.dispatch(request, _ok_call_next)
    assert response.status_code == 200


@pytest.mark.anyio
async def test_missing_allowlist_in_config_passes_all() -> None:
    """When allowed_origins key is absent from config, all origins are permitted."""
    ch = _make_channel_mock(allowed_origins=None)  # key not set in config
    mw = _build_middleware()
    request = _make_request(
        f"{STOREFRONT_PREFIX}/products",
        origin="https://anybody.com",
        channel_id=_FAKE_CHANNEL_ID,
    )
    with patch("app.db.session.SessionLocal", return_value=_db_mock_for(ch)):
        response = await mw.dispatch(request, _ok_call_next)
    assert response.status_code == 200


@pytest.mark.anyio
async def test_db_error_fails_open() -> None:
    """If the DB lookup raises, the middleware passes through (fail-open)."""
    mw = _build_middleware()
    request = _make_request(
        f"{STOREFRONT_PREFIX}/products",
        origin="https://evil.com",
        channel_id=_FAKE_CHANNEL_ID,
    )
    with patch("app.db.session.SessionLocal", side_effect=Exception("DB down")):
        response = await mw.dispatch(request, _ok_call_next)
    assert response.status_code == 200


@pytest.mark.anyio
async def test_non_storefront_route_not_checked() -> None:
    """Admin and other routes are never touched by the origin middleware."""
    mw = _build_middleware()
    request = _make_request(
        "/v1/admin/channels",
        origin="https://evil.com",
        channel_id=_FAKE_CHANNEL_ID,
    )
    with patch("app.db.session.SessionLocal") as mock_session:
        response = await mw.dispatch(request, _ok_call_next)
    # Non-storefront path skips the check entirely
    mock_session.assert_not_called()
    assert response.status_code == 200


@pytest.mark.anyio
async def test_missing_channel_id_header_passes_through() -> None:
    """Requests without X-Channel-Id pass through (downstream will 422/403)."""
    mw = _build_middleware()
    request = _make_request(
        f"{STOREFRONT_PREFIX}/products",
        origin="https://evil.com",
        channel_id=None,  # no channel ID
    )
    with patch("app.db.session.SessionLocal") as mock_session:
        response = await mw.dispatch(request, _ok_call_next)
    mock_session.assert_not_called()
    assert response.status_code == 200
