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
