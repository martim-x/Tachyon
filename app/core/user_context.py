"""Единственный источник текущего пользователя (docs/02 «Изоляция данных», механизм 2).

Паттерн ambient context: контекст ставится выше по стеку (middleware или
зависимость FastAPI, декодирующая JWT) и читается ниже без прокидывания
аргументов. Ни один сервисный метод не принимает user_id аргументом: если
методу нужно понять, чьи это данные, он спрашивает контекст.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from uuid import UUID

from app.core.errors import PermissionDenied

_user_id: ContextVar[UUID | None] = ContextVar("user_id", default=None)


def set_current_user(user_id: UUID) -> Token[UUID | None]:
    """Поставить контекст пользователя, вернуть токен для сброса."""
    return _user_id.set(user_id)


def reset_current_user(token: Token[UUID | None]) -> None:
    """Снять контекст по токену от set_current_user."""
    _user_id.reset(token)


def get_current_user() -> UUID:
    """Текущий пользователь; без контекста это исключение, а не пустая выдача."""
    user_id = _user_id.get()
    if user_id is None:
        raise PermissionDenied("нет контекста пользователя")
    return user_id


@contextmanager
def user_scope(user_id: UUID) -> Iterator[None]:
    """Временный контекст пользователя: для middleware, сервисов и тестов."""
    token = set_current_user(user_id)
    try:
        yield
    finally:
        reset_current_user(token)
