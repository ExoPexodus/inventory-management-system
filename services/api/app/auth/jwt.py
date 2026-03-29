import time
from typing import Any
from uuid import UUID

from jose import jwt

from app.config import settings


def create_operator_access_token(
    *,
    operator_id: UUID,
    tenant_id: UUID,
) -> tuple[str, int]:
    now = int(time.time())
    ttl_sec = settings.jwt_access_expire_minutes * 60
    exp = now + ttl_sec
    payload: dict[str, Any] = {
        "sub": str(operator_id),
        "tenant_id": str(tenant_id),
        "typ": "operator",
        "iat": now,
        "exp": exp,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, ttl_sec


def create_access_token(
    *,
    device_id: UUID,
    tenant_id: UUID,
    shop_ids: list[UUID],
) -> tuple[str, int]:
    now = int(time.time())
    ttl_sec = settings.jwt_access_expire_minutes * 60
    exp = now + ttl_sec
    payload: dict[str, Any] = {
        "sub": str(device_id),
        "tenant_id": str(tenant_id),
        "shop_ids": [str(s) for s in shop_ids],
        "typ": "device",
        "iat": now,
        "exp": exp,
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, ttl_sec


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
