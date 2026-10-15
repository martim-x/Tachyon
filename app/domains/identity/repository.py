from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Conflict
from app.domains.identity.models import User


class UserRepository:
    """Доступ к учётным записям пользователей.
    Scoped Repository здесь применять нельзя, User является субъектом авторизации
    и не содержит отдельного поля user_id.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == email.lower())
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def create(self, *, email: str, password_hash: str) -> User:
        user = User(
            email=email.lower(),
            password_hash=password_hash,
        )
        self._session.add(user)

        try:
            await self._session.flush()
        except IntegrityError as error:
            await self._session.rollback()
            raise Conflict("Email уже занят", safe_message="Email уже занят") from error

        return user
