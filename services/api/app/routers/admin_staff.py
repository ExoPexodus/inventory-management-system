"""Admin staff and employee onboarding endpoints."""

from __future__ import annotations

import bcrypt
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, AdminContext
from app.auth.deps import DeviceAuth, get_device_auth
from app.config import settings
from app.db.admin_deps_db import get_db_admin
from app.db.session import get_db
from app.models import Employee, EnrollmentToken, Shop, TenantEmailConfig
from app.services.email_service import decrypt_secret, encrypt_secret, send_tenant_email
from app.services.enrollment import hash_token

router = APIRouter(prefix="/v1", tags=["Admin Staff"])


def _require_operator_tenant(ctx: AdminContext) -> UUID:
    if ctx.is_legacy_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Legacy admin token is not allowed for this endpoint",
        )
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator is not assigned to a tenant",
        )
    return ctx.tenant_id


def _hash_credential(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def _credential_valid(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False


def _resolve_shop_for_employee(
    db: Session,
    *,
    tenant_id: UUID,
    requested_shop_id: UUID | None,
) -> UUID:
    shops = db.execute(select(Shop).where(Shop.tenant_id == tenant_id).order_by(Shop.created_at.asc())).scalars().all()
    if not shops:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No shops configured for tenant")
    if requested_shop_id is not None:
        if not any(s.id == requested_shop_id for s in shops):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found for tenant")
        return requested_shop_id
    if len(shops) == 1:
        return shops[0].id
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="shop_id is required when tenant has multiple shops",
    )


def _get_employee_for_tenant(db: Session, *, tenant_id: UUID, employee_id: UUID) -> Employee:
    row = db.get(Employee, employee_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    if row.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access is forbidden")
    return row


def _create_enrollment_token(
    db: Session,
    *,
    tenant_id: UUID,
    shop_id: UUID,
    employee_id: UUID,
    ttl_hours: int,
) -> tuple[str, datetime]:
    raw = secrets.token_urlsafe(24)
    expires_at = datetime.now(UTC) + timedelta(hours=ttl_hours)
    db.add(
        EnrollmentToken(
            tenant_id=tenant_id,
            shop_id=shop_id,
            employee_id=employee_id,
            token_hash=hash_token(raw),
            expires_at=expires_at,
        )
    )
    db.flush()
    return raw, expires_at


def _qr_payload(*, employee_id: UUID, token: str) -> dict[str, str | int]:
    return {
        "v": 1,
        "api": settings.public_api_url.rstrip("/"),
        "tok": token,
        "eid": str(employee_id),
    }


class EmployeeOut(BaseModel):
    id: UUID
    tenant_id: UUID
    shop_id: UUID
    name: str
    email: str
    phone: str | None
    position: str
    credential_type: str
    device_id: UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CreateEmployeeBody(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=64)
    position: str = Field(default="cashier", min_length=1, max_length=64)
    credential_type: str = Field(default="pin")
    initial_credential: str = Field(min_length=4, max_length=128)
    shop_id: UUID | None = None

    @model_validator(mode="after")
    def validate_credential_type(self) -> "CreateEmployeeBody":
        ctype = self.credential_type.strip().lower()
        if ctype not in {"pin", "password"}:
            raise ValueError("credential_type must be pin or password")
        if ctype == "pin" and not self.initial_credential.isdigit():
            raise ValueError("pin credential must be numeric")
        self.credential_type = ctype
        return self


class PatchEmployeeBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=64)
    position: str | None = Field(default=None, min_length=1, max_length=64)
    shop_id: UUID | None = None
    is_active: bool | None = None


class InviteMethodBody(BaseModel):
    method: str = Field(pattern="^(qr|email)$")
    ttl_hours: int = Field(default=168, ge=1, le=24 * 30)


class InviteEmployeeResponse(BaseModel):
    employee_id: UUID
    method: str
    expires_at: datetime
    enrollment_token: str | None = None
    qr_payload: dict[str, str | int] | None = None
    email_sent: bool = False


class ResetCredentialsBody(BaseModel):
    credential_type: str = Field(pattern="^(pin|password)$")
    credential: str = Field(min_length=4, max_length=128)

    @model_validator(mode="after")
    def validate_payload(self) -> "ResetCredentialsBody":
        if self.credential_type == "pin" and not self.credential.isdigit():
            raise ValueError("pin credential must be numeric")
        return self


class EmployeeLoginBody(BaseModel):
    credential: str = Field(min_length=1, max_length=128)
    employee_id: UUID | None = None
    email: EmailStr | None = None


class EmployeeLoginResponse(BaseModel):
    employee_id: UUID
    name: str
    email: str
    position: str
    credential_type: str


class TenantEmailConfigPutBody(BaseModel):
    provider: str = Field(pattern="^(smtp|sendgrid)$")
    smtp_host: str | None = None
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: str | None = None
    api_key: str | None = None
    from_email: EmailStr
    from_name: str | None = Field(default=None, max_length=255)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_provider_fields(self) -> "TenantEmailConfigPutBody":
        if self.provider == "smtp":
            if not self.smtp_host or not self.smtp_port:
                raise ValueError("smtp_host and smtp_port are required for smtp provider")
        if self.provider == "sendgrid":
            if not self.api_key:
                raise ValueError("api_key is required for sendgrid provider")
        return self


class TenantEmailConfigOut(BaseModel):
    provider: str
    smtp_host: str | None
    smtp_port: int | None
    smtp_username: str | None
    from_email: str
    from_name: str | None
    is_active: bool
    has_smtp_password: bool
    has_api_key: bool


class TenantEmailTestBody(BaseModel):
    to_email: EmailStr


@router.get("/admin/employees", response_model=list[EmployeeOut])
def list_employees(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    shop_id: UUID | None = None,
) -> list[EmployeeOut]:
    tenant_id = _require_operator_tenant(ctx)
    stmt = select(Employee).where(Employee.tenant_id == tenant_id).order_by(Employee.created_at.desc())
    if shop_id is not None:
        stmt = stmt.where(Employee.shop_id == shop_id)
    rows = db.execute(stmt).scalars().all()
    return [
        EmployeeOut(
            id=r.id,
            tenant_id=r.tenant_id,
            shop_id=r.shop_id,
            name=r.name,
            email=r.email,
            phone=r.phone,
            position=r.position,
            credential_type=r.credential_type,
            device_id=r.device_id,
            is_active=r.is_active,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.post("/admin/employees", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
def create_employee(
    body: CreateEmployeeBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> EmployeeOut:
    tenant_id = _require_operator_tenant(ctx)
    shop_id = _resolve_shop_for_employee(db, tenant_id=tenant_id, requested_shop_id=body.shop_id)
    row = Employee(
        tenant_id=tenant_id,
        shop_id=shop_id,
        name=body.name.strip(),
        email=body.email.strip().lower(),
        phone=body.phone.strip() if body.phone else None,
        position=body.position.strip().lower(),
        credential_type=body.credential_type,
        credential_hash=_hash_credential(body.initial_credential.strip()),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee email already exists") from None
    db.refresh(row)
    return EmployeeOut(
        id=row.id,
        tenant_id=row.tenant_id,
        shop_id=row.shop_id,
        name=row.name,
        email=row.email,
        phone=row.phone,
        position=row.position,
        credential_type=row.credential_type,
        device_id=row.device_id,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/admin/employees/{employee_id}", response_model=EmployeeOut)
def get_employee(
    employee_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> EmployeeOut:
    tenant_id = _require_operator_tenant(ctx)
    row = _get_employee_for_tenant(db, tenant_id=tenant_id, employee_id=employee_id)
    return EmployeeOut(
        id=row.id,
        tenant_id=row.tenant_id,
        shop_id=row.shop_id,
        name=row.name,
        email=row.email,
        phone=row.phone,
        position=row.position,
        credential_type=row.credential_type,
        device_id=row.device_id,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.patch("/admin/employees/{employee_id}", response_model=EmployeeOut)
def patch_employee(
    employee_id: UUID,
    body: PatchEmployeeBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> EmployeeOut:
    tenant_id = _require_operator_tenant(ctx)
    row = _get_employee_for_tenant(db, tenant_id=tenant_id, employee_id=employee_id)
    patch = body.model_dump(exclude_unset=True)
    if "name" in patch and patch["name"] is not None:
        row.name = patch["name"].strip()
    if "email" in patch and patch["email"] is not None:
        row.email = str(patch["email"]).strip().lower()
    if "phone" in patch:
        row.phone = patch["phone"].strip() if isinstance(patch["phone"], str) and patch["phone"].strip() else None
    if "position" in patch and patch["position"] is not None:
        row.position = patch["position"].strip().lower()
    if "shop_id" in patch:
        row.shop_id = _resolve_shop_for_employee(db, tenant_id=tenant_id, requested_shop_id=patch["shop_id"])
    if "is_active" in patch and patch["is_active"] is not None:
        row.is_active = patch["is_active"]
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee email already exists") from None
    db.refresh(row)
    return EmployeeOut(
        id=row.id,
        tenant_id=row.tenant_id,
        shop_id=row.shop_id,
        name=row.name,
        email=row.email,
        phone=row.phone,
        position=row.position,
        credential_type=row.credential_type,
        device_id=row.device_id,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.delete("/admin/employees/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_employee(
    employee_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_operator_tenant(ctx)
    row = _get_employee_for_tenant(db, tenant_id=tenant_id, employee_id=employee_id)
    row.is_active = False
    db.commit()


@router.post("/admin/employees/{employee_id}/invite", response_model=InviteEmployeeResponse)
def invite_employee(
    employee_id: UUID,
    body: InviteMethodBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> InviteEmployeeResponse:
    tenant_id = _require_operator_tenant(ctx)
    employee = _get_employee_for_tenant(db, tenant_id=tenant_id, employee_id=employee_id)
    token, expires_at = _create_enrollment_token(
        db,
        tenant_id=tenant_id,
        shop_id=employee.shop_id,
        employee_id=employee.id,
        ttl_hours=body.ttl_hours,
    )
    payload = _qr_payload(employee_id=employee.id, token=token)
    email_sent = False
    if body.method == "email":
        cfg = db.execute(
            select(TenantEmailConfig).where(
                TenantEmailConfig.tenant_id == tenant_id,
                TenantEmailConfig.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if cfg is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant email configuration is missing")
        send_tenant_email(
            cfg,
            to_email=employee.email,
            subject="Device enrollment invite",
            text_body=(
                f"Hello {employee.name},\n\n"
                f"Use this enrollment token in the cashier app: {token}\n"
                f"QR payload: {payload}\n"
                f"Expires at: {expires_at.isoformat()}\n"
            ),
        )
        email_sent = True
    db.commit()
    return InviteEmployeeResponse(
        employee_id=employee.id,
        method=body.method,
        expires_at=expires_at,
        enrollment_token=token if body.method == "qr" else None,
        qr_payload=payload,
        email_sent=email_sent,
    )


@router.post("/admin/employees/{employee_id}/re-enroll", response_model=InviteEmployeeResponse)
def re_enroll_employee(
    employee_id: UUID,
    body: InviteMethodBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> InviteEmployeeResponse:
    tenant_id = _require_operator_tenant(ctx)
    employee = _get_employee_for_tenant(db, tenant_id=tenant_id, employee_id=employee_id)
    employee.device_id = None
    token, expires_at = _create_enrollment_token(
        db,
        tenant_id=tenant_id,
        shop_id=employee.shop_id,
        employee_id=employee.id,
        ttl_hours=body.ttl_hours,
    )
    payload = _qr_payload(employee_id=employee.id, token=token)
    email_sent = False
    if body.method == "email":
        cfg = db.execute(
            select(TenantEmailConfig).where(
                TenantEmailConfig.tenant_id == tenant_id,
                TenantEmailConfig.is_active.is_(True),
            )
        ).scalar_one_or_none()
        if cfg is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant email configuration is missing")
        send_tenant_email(
            cfg,
            to_email=employee.email,
            subject="Device re-enrollment invite",
            text_body=(
                f"Hello {employee.name},\n\n"
                f"Use this re-enrollment token in the cashier app: {token}\n"
                f"QR payload: {payload}\n"
                f"Expires at: {expires_at.isoformat()}\n"
            ),
        )
        email_sent = True
    db.commit()
    return InviteEmployeeResponse(
        employee_id=employee.id,
        method=body.method,
        expires_at=expires_at,
        enrollment_token=token if body.method == "qr" else None,
        qr_payload=payload,
        email_sent=email_sent,
    )


@router.post("/admin/employees/{employee_id}/reset-credentials", response_model=EmployeeOut)
def reset_employee_credentials(
    employee_id: UUID,
    body: ResetCredentialsBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> EmployeeOut:
    tenant_id = _require_operator_tenant(ctx)
    row = _get_employee_for_tenant(db, tenant_id=tenant_id, employee_id=employee_id)
    row.credential_type = body.credential_type
    row.credential_hash = _hash_credential(body.credential.strip())
    db.commit()
    db.refresh(row)
    return EmployeeOut(
        id=row.id,
        tenant_id=row.tenant_id,
        shop_id=row.shop_id,
        name=row.name,
        email=row.email,
        phone=row.phone,
        position=row.position,
        credential_type=row.credential_type,
        device_id=row.device_id,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/employees/login", response_model=EmployeeLoginResponse)
def employee_login(
    body: EmployeeLoginBody,
    auth: Annotated[DeviceAuth, Depends(get_device_auth)],
    db: Annotated[Session, Depends(get_db)],
) -> EmployeeLoginResponse:
    stmt = select(Employee).where(
        Employee.tenant_id == auth.tenant_id,
        Employee.device_id == auth.device_id,
        Employee.is_active.is_(True),
    )
    if body.employee_id is not None:
        stmt = stmt.where(Employee.id == body.employee_id)
    if body.email is not None:
        stmt = stmt.where(Employee.email == str(body.email).strip().lower())
    rows = db.execute(stmt.order_by(Employee.created_at.asc())).scalars().all()
    row = rows[0] if rows else None
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Employee is not linked to this device")
    if not _credential_valid(body.credential.strip(), row.credential_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid employee credential")
    return EmployeeLoginResponse(
        employee_id=row.id,
        name=row.name,
        email=row.email,
        position=row.position,
        credential_type=row.credential_type,
    )


@router.get("/admin/tenant-settings/email", response_model=TenantEmailConfigOut)
def get_tenant_email_settings(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> TenantEmailConfigOut:
    tenant_id = _require_operator_tenant(ctx)
    row = db.execute(select(TenantEmailConfig).where(TenantEmailConfig.tenant_id == tenant_id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email settings not configured")
    return TenantEmailConfigOut(
        provider=row.provider,
        smtp_host=row.smtp_host,
        smtp_port=row.smtp_port,
        smtp_username=row.smtp_username,
        from_email=row.from_email,
        from_name=row.from_name,
        is_active=row.is_active,
        has_smtp_password=bool(decrypt_secret(row.smtp_password_encrypted)),
        has_api_key=bool(decrypt_secret(row.api_key_encrypted)),
    )


@router.put("/admin/tenant-settings/email", response_model=TenantEmailConfigOut)
def put_tenant_email_settings(
    body: TenantEmailConfigPutBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> TenantEmailConfigOut:
    tenant_id = _require_operator_tenant(ctx)
    row = db.execute(select(TenantEmailConfig).where(TenantEmailConfig.tenant_id == tenant_id)).scalar_one_or_none()
    if row is None:
        row = TenantEmailConfig(tenant_id=tenant_id, provider=body.provider, from_email=str(body.from_email))
        db.add(row)
    row.provider = body.provider
    row.smtp_host = body.smtp_host.strip() if body.smtp_host else None
    row.smtp_port = body.smtp_port
    row.smtp_username = body.smtp_username.strip() if body.smtp_username else None
    if body.smtp_password is not None:
        row.smtp_password_encrypted = encrypt_secret(body.smtp_password)
    if body.api_key is not None:
        row.api_key_encrypted = encrypt_secret(body.api_key)
    row.from_email = str(body.from_email).strip().lower()
    row.from_name = body.from_name.strip() if body.from_name else None
    row.is_active = body.is_active
    db.commit()
    db.refresh(row)
    return TenantEmailConfigOut(
        provider=row.provider,
        smtp_host=row.smtp_host,
        smtp_port=row.smtp_port,
        smtp_username=row.smtp_username,
        from_email=row.from_email,
        from_name=row.from_name,
        is_active=row.is_active,
        has_smtp_password=bool(decrypt_secret(row.smtp_password_encrypted)),
        has_api_key=bool(decrypt_secret(row.api_key_encrypted)),
    )


@router.post("/admin/tenant-settings/email/test")
def test_tenant_email_settings(
    body: TenantEmailTestBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> dict[str, str]:
    tenant_id = _require_operator_tenant(ctx)
    row = db.execute(
        select(TenantEmailConfig).where(TenantEmailConfig.tenant_id == tenant_id, TenantEmailConfig.is_active.is_(True))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email settings not configured")
    send_tenant_email(
        row,
        to_email=str(body.to_email),
        subject="Inventory system email test",
        text_body="Your tenant email settings are configured correctly.",
    )
    return {"status": "ok"}
