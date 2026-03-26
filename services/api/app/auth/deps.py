from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.auth.jwt import decode_token
from app.db.rls import set_rls_context
from app.db.session import get_db
from app.models import Device

security = HTTPBearer(auto_error=False)


class DeviceAuth:
    def __init__(self, device_id: UUID, tenant_id: UUID, shop_ids: list[UUID]):
        self.device_id = device_id
        self.tenant_id = tenant_id
        self.shop_ids = shop_ids


def get_device_auth(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[Session, Depends(get_db)],
) -> DeviceAuth:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    try:
        payload = decode_token(creds.credentials)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if payload.get("typ") != "device":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type")
    try:
        device_id = UUID(payload["sub"])
        tenant_id = UUID(payload["tenant_id"])
        shop_ids = [UUID(x) for x in payload.get("shop_ids", [])]
    except (KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token")
    set_rls_context(db, is_admin=False, tenant_id=tenant_id)
    device = db.get(Device, device_id)
    if device is None or device.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Device not found")
    return DeviceAuth(device_id=device_id, tenant_id=tenant_id, shop_ids=shop_ids)
