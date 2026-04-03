from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.enrollment import enroll_device, refresh_device_tokens

router = APIRouter(prefix="/v1/devices", tags=["Devices"])


class EnrollRequest(BaseModel):
    enrollment_token: str
    device_fingerprint: str
    platform: str = "android"


class EnrollResponse(BaseModel):
    access_token: str
    refresh_token: str
    tenant_id: UUID
    shop_ids: list[UUID]
    expires_in: int
    employee_id: UUID | None = None
    employee_name: str | None = None
    employee_credential_type: str | None = None


@router.post("/enroll", response_model=EnrollResponse)
def enroll(
    body: EnrollRequest,
    db: Annotated[Session, Depends(get_db)],
) -> EnrollResponse:
    try:
        access, refresh, tenant_id, shops, ttl, employee_id, employee_name, employee_credential_type = enroll_device(
            db,
            raw_enrollment_token=body.enrollment_token,
            fingerprint=body.device_fingerprint,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired enrollment token",
        )
    return EnrollResponse(
        access_token=access,
        refresh_token=refresh,
        tenant_id=tenant_id,
        shop_ids=shops,
        expires_in=ttl,
        employee_id=employee_id,
        employee_name=employee_name,
        employee_credential_type=employee_credential_type,
    )


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=EnrollResponse)
def refresh_tokens(
    body: RefreshRequest,
    db: Annotated[Session, Depends(get_db)],
) -> EnrollResponse:
    try:
        access, refresh, tenant_id, shops, ttl = refresh_device_tokens(
            db, raw_refresh_token=body.refresh_token
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    return EnrollResponse(
        access_token=access,
        refresh_token=refresh,
        tenant_id=tenant_id,
        shop_ids=shops,
        expires_in=ttl,
    )
