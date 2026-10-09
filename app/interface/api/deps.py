from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthenticationFailed
from app.core.persistence import get_session
from app.core.user_context import reset_current_user, set_current_user
from app.domains.identity.models import User
from app.domains.identity.repository import UserRepository
from app.domains.identity.service import decode_access_token

SessionDep = Annotated[
    AsyncSession,
    Depends(get_session, scope="function"),
]

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    session: SessionDep,
) -> AsyncIterator[User]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationFailed("Отсутствует Bearer-токен")

    user_id = decode_access_token(credentials.credentials)
    user = await UserRepository(session).get_by_id(user_id)

    if user is None:
        raise AuthenticationFailed("Пользователь токена не найден")

    context_token = set_current_user(user.id)
    try:
        yield user
    finally:
        reset_current_user(context_token)


CurrentUser = Annotated[
    User,
    Depends(get_current_user, scope="function"),
]
