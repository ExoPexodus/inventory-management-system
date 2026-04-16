from __future__ import annotations

from typing import Annotated

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import create_operator_token
from app.db.session import get_db
from app.models import PlatformOperator
from app.services.audit_service import write_audit

router = APIRouter(prefix="/v1/platform/auth", tags=["Platform Auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    expires_in: int
    operator_id: str
    email: str
    display_name: str


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> LoginResponse:
    operator = db.execute(
        select(PlatformOperator).where(PlatformOperator.email == body.email.lower())
    ).scalar_one_or_none()

    if operator is None or not operator.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    if not bcrypt.checkpw(body.password.encode(), operator.password_hash.encode()):
        write_audit(db, operator_id=None, action="login_failed", resource_type="platform_operator", details={"email": body.email})
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token, ttl = create_operator_token(operator.id, operator.email)
    write_audit(db, operator_id=operator.id, action="login_success", resource_type="platform_operator")
    db.commit()

    return LoginResponse(
        access_token=token,
        expires_in=ttl,
        operator_id=str(operator.id),
        email=operator.email,
        display_name=operator.display_name,
    )
