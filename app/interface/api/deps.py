from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, SystemClock
from app.core.errors import AuthenticationFailed
from app.core.persistence import get_session
from app.core.user_context import (
    reset_current_user,
    set_current_user,
)
from app.domains.identity.models import User
from app.domains.identity.repository import UserRepository
from app.domains.identity.service import decode_access_token
from app.interface.export.base import ReportExporter
from app.interface.export.xlsx import XlsxReportExporter


def get_clock() -> Clock:
    """Системные часы приложения, заменяемые в тестах."""

    return SystemClock()


ClockDep = Annotated[
    Clock,
    Depends(get_clock),
]

SessionDep = Annotated[
    AsyncSession,
    Depends(get_session, scope="function"),
]

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    session: SessionDep,
) -> AsyncIterator[User]:
    # Токен можно передать через заголовок Authorization: Bearer ...
    # (API-клиенты) либо через cookie access_token (браузерная сессия
    # на страницах дашборда). Cookie имеет низший приоритет: явный
    # заголовок всегда выигрывает.
    token: str | None = None
    if credentials is not None and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    if token is None:
        token = request.cookies.get("access_token")

    if token is None:
        raise AuthenticationFailed("Отсутствует Bearer-токен")

    user_id = decode_access_token(token)
    user = await UserRepository(session).get_by_id(user_id)

    if user is None:
        raise AuthenticationFailed("Пользователь токена не найден")

    context_token = set_current_user(user.id)

    try:
        yield user
    finally:
        reset_current_user(context_token)


def get_xlsx_report_exporter() -> ReportExporter:
    """Адаптер экспорта собирается снаружи доменов (docs/02 §export).

    Подменяемая зависимость: тесты с FakeExporter не создают ни одного
    реального файла.
    """

    return XlsxReportExporter()


ExportDep = Annotated[
    ReportExporter,
    Depends(get_xlsx_report_exporter, scope="function"),
]

CurrentUser = Annotated[
    User,
    Depends(get_current_user, scope="function"),
]
