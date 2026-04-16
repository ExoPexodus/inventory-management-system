from uuid import UUID

from sqlalchemy.orm import Session

from app.models import PlatformAuditLog


def write_audit(
    db: Session,
    *,
    operator_id: UUID | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
) -> None:
    db.add(
        PlatformAuditLog(
            operator_id=operator_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
        )
    )
