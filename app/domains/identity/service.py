from datetime import UTC, datetime, timedelta
from uuid import UUID

import bcrypt
import jwt
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.errors import AuthenticationFailed, Conflict
from app.domains.identity.models import User
from app.domains.identity.repository import UserRepository

JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


DUMMY_PASSWORD_HASH = hash_password("dummy-password")


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


class IdentityService:
    """Сценарии регистрации и проверки учётных данных."""

    def __init__(self, repository: UserRepository) -> None:
        self._repository = repository

    async def register(self, *, email: str, password: str) -> User:
        normalized_email = email.lower()

        if await self._repository.get_by_email(normalized_email) is not None:
            raise Conflict("Email уже занят")

        password_hash = await run_in_threadpool(hash_password, password)

        return await self._repository.create(
            email=normalized_email,
            password_hash=password_hash,
        )

    async def authenticate(self, *, email: str, password: str) -> User:
        user = await self._repository.get_by_email(email.lower())
        password_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH

        password_is_valid = await run_in_threadpool(
            verify_password,
            password,
            password_hash,
        )

        if user is None or not password_is_valid:
            # Одинаковые ответ и стоимость bcrypt не раскрывают существование email.
            raise AuthenticationFailed("Неверный email или пароль")

        return user
