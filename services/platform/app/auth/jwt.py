from datetime import UTC, datetime, timedelta
from uuid import UUID

from jose import JWTError, jwt

from app.config import settings

ALGORITHM = "HS256"


def create_operator_token(operator_id: UUID, email: str) -> tuple[str, int]:
    ttl = settings.jwt_access_expire_minutes
    payload = {
        "sub": str(operator_id),
        "email": email,
        "typ": "platform_operator",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=ttl),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)
    return token, ttl * 60


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
