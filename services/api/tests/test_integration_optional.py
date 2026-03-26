"""Optional smoke against a live API (docker compose). Run: IMS_INTEGRATION=1 IMS_API_BASE=http://127.0.0.1:8001 pytest tests/test_integration_optional.py -v"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("IMS_INTEGRATION") != "1",
    reason="Set IMS_INTEGRATION=1 and IMS_API_BASE (optional) for live API checks",
)


def test_health_live() -> None:
    import httpx

    base = os.getenv("IMS_API_BASE", "http://127.0.0.1:8001").rstrip("/")
    r = httpx.get(f"{base}/health", timeout=10.0)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"
