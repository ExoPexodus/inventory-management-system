"""Admin staff and employee onboarding endpoints.

After the Employee+AdminUser → User merge, "employees" are Users whose role grants
cashier_app:access. Their credentials live in the `pin_hash` or `password_hash`
columns (both nullable, set at enrollment time).
"""

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

from app.auth.admin_deps import AdminAuthDep, AdminContext, require_permission
from app.auth.deps import DeviceAuth, get_device_auth
from app.config import settings
from app.db.admin_deps_db import get_db_admin
from app.db.session import get_db
from app.models import EnrollmentToken, Role, Shop, TenantEmailConfig, User
from app.services.audit_service import write_audit
from app.services.email_service import decrypt_secret, encrypt_secret, send_tenant_email
from app.services.enrollment import hash_token
from app.services.permission_service import get_role_permissions

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


def _credential_valid(raw: str, hashed: str | None) -> bool:
    if not hashed:
        return False
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


def _resolve_role_for_position(db: Session, tenant_id: UUID, position: str) -> UUID:
    """Map an employee 'position' string to a matching role. Creates the role if missing."""
    pos = position.strip().lower()
    role = db.execute(
        select(Role).where(Role.tenant_id == tenant_id, Role.name == pos)
    ).scalar_one_or_none()
    if role is None:
        # Create a custom role with no permissions — admin configures permissions later
        role = Role(tenant_id=tenant_id, name=pos, display_name=pos.replace("_", " ").title(), is_system=False)
        db.add(role)
        db.flush()
    return role.id


def _get_employee_for_tenant(db: Session, *, tenant_id: UUID, employee_id: UUID) -> User:
    row = db.get(User, employee_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    if row.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access is forbidden")
    return row


def _create_enrollment_token(
    db: Session,
    *,
    tenant_id: UUID,
    shop_id: UUID | None,
    user_id: UUID,
    ttl_hours: int,
    app_target: str = "cashier",
) -> tuple[str, datetime]:
    raw = secrets.token_urlsafe(24)
    expires_at = datetime.now(UTC) + timedelta(hours=ttl_hours)
    db.add(
        EnrollmentToken(
            tenant_id=tenant_id,
            shop_id=shop_id,
            user_id=user_id,
            app_target=app_target,
            token_hash=hash_token(raw),
            expires_at=expires_at,
        )
    )
    db.flush()
    return raw, expires_at


def _qr_payload(*, user_id: UUID, token: str, app_target: str = "cashier") -> dict[str, str | int]:
    return {
        "v": 1,
        "api": settings.public_api_url.rstrip("/"),
        "tok": token,
        "eid": str(user_id),  # kept as 'eid' for backward compat with existing cashier app
        "app": app_target,
    }


def _position_for_user(db: Session, user: User) -> str:
    """Derive a legacy-style position string from the user's role name."""
    if user.role:
        return user.role.name
    return "unknown"


def _credential_type_for_user(user: User) -> str:
    if user.pin_hash:
        return "pin"
    if user.password_hash:
        return "password"
    return "none"


class EmployeeOut(BaseModel):
    id: UUID
    tenant_id: UUID
    shop_id: UUID | None
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
    app_target: str = Field(default="cashier", pattern="^(cashier|admin_mobile)$")


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


def _employee_out(db: Session, user: User) -> EmployeeOut:
    return EmployeeOut(
        id=user.id,
        tenant_id=user.tenant_id,
        shop_id=user.shop_id,
        name=user.name,
        email=user.email,
        phone=user.phone,
        position=_position_for_user(db, user),
        credential_type=_credential_type_for_user(user),
        device_id=user.device_id,
        is_active=user.is_active,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.get("/admin/employees", response_model=list[EmployeeOut], dependencies=[require_permission("staff:read")])
def list_employees(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
    shop_id: UUID | None = None,
    include_inactive: bool = False,
) -> list[EmployeeOut]:
    """Lists users whose role has cashier_app:access (legacy 'employees' concept).

    After the User merge, this filters on role permission rather than a separate table.
    """
    tenant_id = _require_operator_tenant(ctx)
    from app.models import Permission, RolePermission

    stmt = (
        select(User)
        .join(Role, User.role_id == Role.id)
        .join(RolePermission, RolePermission.role_id == Role.id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(
            User.tenant_id == tenant_id,
            Permission.codename == "cashier_app:access",
        )
        .distinct()
        .order_by(User.created_at.desc())
    )
    if not include_inactive:
        stmt = stmt.where(User.is_active.is_(True))
    if shop_id is not None:
        stmt = stmt.where(User.shop_id == shop_id)
    rows = db.execute(stmt).scalars().all()
    return [_employee_out(db, r) for r in rows]


@router.post("/admin/employees", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED, dependencies=[require_permission("staff:write")])
def create_employee(
    body: CreateEmployeeBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> EmployeeOut:
    tenant_id = _require_operator_tenant(ctx)
    # shop_id is optional — admin mobile users have no shop (sees all shops).
    # For cashier users with no explicit shop, auto-assign when there's only one shop.
    if body.shop_id is None:
        shops = db.execute(select(Shop).where(Shop.tenant_id == tenant_id)).scalars().all()
        shop_id: UUID | None = shops[0].id if len(shops) == 1 else None
    else:
        shop_id = _resolve_shop_for_employee(db, tenant_id=tenant_id, requested_shop_id=body.shop_id)
    role_id = _resolve_role_for_position(db, tenant_id, body.position)
    hashed = _hash_credential(body.initial_credential.strip())
    row = User(
        tenant_id=tenant_id,
        shop_id=shop_id,
        role_id=role_id,
        name=body.name.strip(),
        email=body.email.strip().lower(),
        phone=body.phone.strip() if body.phone else None,
        pin_hash=hashed if body.credential_type == "pin" else None,
        password_hash=hashed if body.credential_type == "password" else None,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee email already exists") from None
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.user_id, action="create_employee", resource_type="user", resource_id=str(row.id))
    db.commit()
    db.refresh(row)
    return _employee_out(db, row)


@router.get("/admin/employees/{employee_id}", response_model=EmployeeOut, dependencies=[require_permission("staff:read")])
def get_employee(
    employee_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> EmployeeOut:
    tenant_id = _require_operator_tenant(ctx)
    row = _get_employee_for_tenant(db, tenant_id=tenant_id, employee_id=employee_id)
    return _employee_out(db, row)


@router.patch("/admin/employees/{employee_id}", response_model=EmployeeOut, dependencies=[require_permission("staff:write")])
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
        row.role_id = _resolve_role_for_position(db, tenant_id, patch["position"])
    if "shop_id" in patch:
        if patch["shop_id"] is None:
            row.shop_id = None
        else:
            row.shop_id = _resolve_shop_for_employee(db, tenant_id=tenant_id, requested_shop_id=patch["shop_id"])
    if "is_active" in patch and patch["is_active"] is not None:
        row.is_active = patch["is_active"]
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.user_id, action="update_employee", resource_type="user", resource_id=str(employee_id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee email already exists") from None
    db.refresh(row)
    return _employee_out(db, row)


@router.delete("/admin/employees/{employee_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[require_permission("staff:write")])
def delete_employee(
    employee_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_operator_tenant(ctx)
    row = _get_employee_for_tenant(db, tenant_id=tenant_id, employee_id=employee_id)
    row.is_active = False
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.user_id, action="deactivate_employee", resource_type="user", resource_id=str(employee_id))
    db.commit()


@router.patch("/admin/employees/{employee_id}/reactivate", response_model=EmployeeOut, dependencies=[require_permission("staff:write")])
def reactivate_employee(
    employee_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> EmployeeOut:
    tenant_id = _require_operator_tenant(ctx)
    row = _get_employee_for_tenant(db, tenant_id=tenant_id, employee_id=employee_id)
    row.is_active = True
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.user_id, action="reactivate_employee", resource_type="user", resource_id=str(employee_id))
    db.commit()
    return _employee_out(db, row)


@router.post("/admin/employees/{employee_id}/invite", response_model=InviteEmployeeResponse, dependencies=[require_permission("staff:write")])
def invite_employee(
    employee_id: UUID,
    body: InviteMethodBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> InviteEmployeeResponse:
    tenant_id = _require_operator_tenant(ctx)
    employee = _get_employee_for_tenant(db, tenant_id=tenant_id, employee_id=employee_id)

    # Verify user has the right access permission for the chosen app target
    if employee.role_id:
        perms = get_role_permissions(db, employee.role_id)
        required = f"{body.app_target}_app:access" if body.app_target == "cashier" else "admin_mobile:access"
        if required not in perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User's role does not grant {required}",
            )

    shop_id = employee.shop_id
    if shop_id is None:
        shops = db.execute(select(Shop).where(Shop.tenant_id == tenant_id)).scalars().all()
        if len(shops) == 1:
            shop_id = shops[0].id
    token, expires_at = _create_enrollment_token(
        db,
        tenant_id=tenant_id,
        shop_id=shop_id,
        user_id=employee.id,
        ttl_hours=body.ttl_hours,
        app_target=body.app_target,
    )
    payload = _qr_payload(user_id=employee.id, token=token, app_target=body.app_target)
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
                f"Use this enrollment token in the app: {token}\n"
                f"QR payload: {payload}\n"
                f"Expires at: {expires_at.isoformat()}\n"
            ),
        )
        email_sent = True
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.user_id, action="invite_employee", resource_type="user", resource_id=str(employee_id))
    db.commit()
    return InviteEmployeeResponse(
        employee_id=employee.id,
        method=body.method,
        expires_at=expires_at,
        enrollment_token=token if body.method == "qr" else None,
        qr_payload=payload,
        email_sent=email_sent,
    )


@router.post("/admin/employees/{employee_id}/re-enroll", response_model=InviteEmployeeResponse, dependencies=[require_permission("staff:write")])
def re_enroll_employee(
    employee_id: UUID,
    body: InviteMethodBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> InviteEmployeeResponse:
    tenant_id = _require_operator_tenant(ctx)
    employee = _get_employee_for_tenant(db, tenant_id=tenant_id, employee_id=employee_id)
    employee.device_id = None
    shop_id = employee.shop_id
    if shop_id is None:
        # Auto-assign only when there is exactly one shop; otherwise keep None
        # (admin mobile sees all shops; cashier with no shop will be assigned at login).
        shops = db.execute(select(Shop).where(Shop.tenant_id == tenant_id)).scalars().all()
        if len(shops) == 1:
            shop_id = shops[0].id
    token, expires_at = _create_enrollment_token(
        db,
        tenant_id=tenant_id,
        shop_id=shop_id,
        user_id=employee.id,
        ttl_hours=body.ttl_hours,
        app_target=body.app_target,
    )
    payload = _qr_payload(user_id=employee.id, token=token, app_target=body.app_target)
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
                f"Use this re-enrollment token in the app: {token}\n"
                f"QR payload: {payload}\n"
                f"Expires at: {expires_at.isoformat()}\n"
            ),
        )
        email_sent = True
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.user_id, action="re_enroll_employee", resource_type="user", resource_id=str(employee_id))
    db.commit()
    return InviteEmployeeResponse(
        employee_id=employee.id,
        method=body.method,
        expires_at=expires_at,
        enrollment_token=token if body.method == "qr" else None,
        qr_payload=payload,
        email_sent=email_sent,
    )


@router.post("/admin/employees/{employee_id}/reset-credentials", response_model=EmployeeOut, dependencies=[require_permission("staff:write")])
def reset_employee_credentials(
    employee_id: UUID,
    body: ResetCredentialsBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> EmployeeOut:
    tenant_id = _require_operator_tenant(ctx)
    row = _get_employee_for_tenant(db, tenant_id=tenant_id, employee_id=employee_id)
    hashed = _hash_credential(body.credential.strip())
    if body.credential_type == "pin":
        row.pin_hash = hashed
    else:
        row.password_hash = hashed
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.user_id, action="reset_credentials", resource_type="user", resource_id=str(employee_id))
    db.commit()
    db.refresh(row)
    return _employee_out(db, row)


@router.post("/employees/login", response_model=EmployeeLoginResponse)
def employee_login(
    body: EmployeeLoginBody,
    auth: Annotated[DeviceAuth, Depends(get_device_auth)],
    db: Annotated[Session, Depends(get_db)],
) -> EmployeeLoginResponse:
    # First check if this device has a deactivated user linked (before filtering by is_active).
    deactivated_stmt = select(User).where(
        User.tenant_id == auth.tenant_id,
        User.device_id == auth.device_id,
        User.is_active.is_(False),
    )
    if body.employee_id is not None:
        deactivated_stmt = deactivated_stmt.where(User.id == body.employee_id)
    if body.email is not None:
        deactivated_stmt = deactivated_stmt.where(User.email == str(body.email).strip().lower())
    if db.execute(deactivated_stmt).scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account deactivated")

    stmt = select(User).where(
        User.tenant_id == auth.tenant_id,
        User.device_id == auth.device_id,
        User.is_active.is_(True),
    )
    if body.employee_id is not None:
        stmt = stmt.where(User.id == body.employee_id)
    if body.email is not None:
        stmt = stmt.where(User.email == str(body.email).strip().lower())
    rows = db.execute(stmt.order_by(User.created_at.asc())).scalars().all()
    row = rows[0] if rows else None
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is not linked to this device")

    # Enforce cashier_app:access on the user's role
    if row.role_id:
        perms = get_role_permissions(db, row.role_id)
        if "cashier_app:access" not in perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your role does not grant cashier app access. Contact your administrator.",
            )

    # Try PIN first, then password (both stored hashed on User)
    credential = body.credential.strip()
    ok = _credential_valid(credential, row.pin_hash) or _credential_valid(credential, row.password_hash)
    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credential")

    return EmployeeLoginResponse(
        employee_id=row.id,
        name=row.name,
        email=row.email,
        position=_position_for_user(db, row),
        credential_type=_credential_type_for_user(row),
    )


@router.get("/admin/tenant-settings/email", response_model=TenantEmailConfigOut, dependencies=[require_permission("settings:read")])
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


@router.put("/admin/tenant-settings/email", response_model=TenantEmailConfigOut, dependencies=[require_permission("settings:write")])
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
    write_audit(db, tenant_id=tenant_id, operator_id=ctx.user_id, action="update_email_settings", resource_type="tenant_email_config")
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


@router.post("/admin/tenant-settings/email/test", dependencies=[require_permission("settings:write")])
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
