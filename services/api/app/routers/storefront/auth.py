"""Storefront auth: resolve channel from X-Channel-Id header."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Channel

_ALLOWED_CHANNEL_TYPES = {"headless", "manual"}


def get_storefront_channel(
    x_channel_id: Annotated[UUID, Header(alias="X-Channel-Id")],
    db: Annotated[Session, Depends(get_db)],
) -> Channel:
    channel = db.get(Channel, x_channel_id)
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Channel {x_channel_id} not found")
    if channel.type not in _ALLOWED_CHANNEL_TYPES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Channel type '{channel.type}' cannot be used as a storefront channel",
        )
    if channel.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"Channel is not active (status={channel.status})")
    return channel


StorefrontChannelDep = Annotated[Channel, Depends(get_storefront_channel)]


from typing import Optional as _Opt
from jose import JWTError as _JWTError


class CustomerAuth:
    def __init__(self, customer_id: UUID, tenant_id: UUID, channel_id: UUID, email: str):
        self.customer_id = customer_id
        self.tenant_id = tenant_id
        self.channel_id = channel_id
        self.email = email


def get_current_customer(
    authorization: Annotated[_Opt[str], Header(alias="Authorization")] = None,
) -> CustomerAuth:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Missing customer token")
    try:
        from app.auth.jwt import decode_token
        payload = decode_token(authorization.split(" ", 1)[1])
    except _JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid customer token")
    if payload.get("typ") != "customer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Wrong token type")
    try:
        return CustomerAuth(
            customer_id=UUID(payload["sub"]),
            tenant_id=UUID(payload["tenant_id"]),
            channel_id=UUID(payload["channel_id"]),
            email=payload["email"],
        )
    except (KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Malformed token")


CustomerAuthDep = Annotated[CustomerAuth, Depends(get_current_customer)]
