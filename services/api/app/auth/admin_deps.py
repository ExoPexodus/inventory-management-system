from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError

from app.auth.jwt import decode_token
from app.config import settings


def _verify_legacy_admin_token(x_admin_token: str | None) -> bool:
    expected = settings.admin_api_token
    if not expected:
        return False
    return bool(x_admin_token and x_admin_token == expected)


def require_admin_context(
    authorization: Annotated[str | None, Header()] = None,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> None:
    """Accepts static X-Admin-Token (legacy) or Bearer JWT from POST /v1/admin/auth/login."""
    if _verify_legacy_admin_token(x_admin_token):
        return

    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization[7:].strip()
        try:
            payload = decode_token(raw)
        except JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid bearer token",
            ) from None
        if payload.get("typ") != "operator":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Wrong token type",
            )
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing admin credentials (X-Admin-Token or Authorization: Bearer)",
    )


AdminAuthDep = Annotated[None, Depends(require_admin_context)]
# Backward-compatible name for routers importing AdminTokenDep
AdminTokenDep = AdminAuthDep
