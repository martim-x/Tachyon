from datetime import UTC, datetime, timedelta
from uuid import UUID

import bcrypt
import jwt

from app.core.config import get_settings
from app.core.errors import AuthenticationFailed

JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except ValueError:
        return False


def create_access_token(
    user_id: UUID,
    *,
    secret_key: str | None = None,
    ttl_minutes: int | None = None,
    now: datetime | None = None,
) -> str:
    settings = get_settings()
    resolved_secret = secret_key if secret_key is not None else settings.secret_key
    resolved_ttl = ttl_minutes if ttl_minutes is not None else settings.token_ttl
    issued_at = now if now is not None else datetime.now(UTC)

    return jwt.encode(
        {
            "sub": str(user_id),
            "iat": issued_at,
            "exp": issued_at + timedelta(minutes=resolved_ttl),
        },
        resolved_secret,
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(
    token: str,
    *,
    secret_key: str | None = None,
) -> UUID:
    settings = get_settings()
    resolved_secret = secret_key if secret_key is not None else settings.secret_key

    try:
        payload = jwt.decode(
            token,
            resolved_secret,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
        return UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as error:
        raise AuthenticationFailed("Недействительный токен") from error