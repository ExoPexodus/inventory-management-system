import hashlib
import secrets
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import create_access_token
from app.db.rls import set_rls_context
from app.models import Device, Employee, EnrollmentToken, Shop


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def enroll_device(
    db: Session,
    *,
    raw_enrollment_token: str,
    fingerprint: str,
) -> tuple[str, str, UUID, list[UUID], int, UUID | None, str | None, str | None]:
    token_hash = hash_token(raw_enrollment_token)
    row = db.execute(
        select(EnrollmentToken).where(
            EnrollmentToken.token_hash == token_hash,
            EnrollmentToken.used_at.is_(None),
            EnrollmentToken.expires_at > datetime.now(UTC),
        )
    ).scalar_one_or_none()
    if row is None:
        raise ValueError("invalid_or_expired_enrollment")

    set_rls_context(db, is_admin=False, tenant_id=row.tenant_id)

    shop = db.get(Shop, row.shop_id)
    if shop is None:
        raise ValueError("shop_missing")

    refresh_raw = secrets.token_urlsafe(48)
    device = Device(
        tenant_id=row.tenant_id,
        default_shop_id=row.shop_id,
        fingerprint=fingerprint,
        refresh_token_hash=hash_token(refresh_raw),
    )
    db.add(device)
    row.used_at = datetime.now(UTC)
    db.flush()
    employee_name: str | None = None
    employee_credential_type: str | None = None
    if row.employee_id is not None:
        employee = db.get(Employee, row.employee_id)
        if employee is not None and employee.tenant_id == row.tenant_id:
            employee.device_id = device.id
            employee_name = employee.name
            employee_credential_type = employee.credential_type

    access, ttl = create_access_token(
        device_id=device.id,
        tenant_id=device.tenant_id,
        shop_ids=[row.shop_id],
    )
    db.commit()
    return access, refresh_raw, device.tenant_id, [row.shop_id], ttl, row.employee_id, employee_name, employee_credential_type


def refresh_device_tokens(
    db: Session,
    *,
    raw_refresh_token: str,
) -> tuple[str, str, UUID, list[UUID], int]:
    """Verify refresh token, rotate it, return new access + refresh."""
    token_hash = hash_token(raw_refresh_token)
    device = db.execute(
        select(Device).where(Device.refresh_token_hash == token_hash)
    ).scalar_one_or_none()
    if device is None:
        raise ValueError("invalid_refresh")

    set_rls_context(db, is_admin=False, tenant_id=device.tenant_id)

    shop_ids = [device.default_shop_id]
    new_refresh = secrets.token_urlsafe(48)
    device.refresh_token_hash = hash_token(new_refresh)
    db.flush()

    access, ttl = create_access_token(
        device_id=device.id,
        tenant_id=device.tenant_id,
        shop_ids=shop_ids,
    )
    db.commit()
    return access, new_refresh, device.tenant_id, shop_ids, ttl
