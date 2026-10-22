"""Доменные исключения проекта (docs/02: errors.py объявляет NotFound и PermissionDenied)."""


class DomainError(Exception):
    """Базовое исключение домена с сообщением для человека."""


class NotFound(DomainError):
    """Объект не найден или принадлежит другому пользователю."""


class PermissionDenied(DomainError):
    """Действие запрещено: например, нет контекста пользователя."""


class AuthenticationFailed(DomainError):
    """Учётные данные или токен не прошли проверку."""


class Conflict(DomainError):
    """Ресурс уже существует и не может быть создан повторно.

    message — внутренний текст для логов; safe_message — единственная
    формулировка, которую обработчик отдаёт клиенту (без email и деталей БД).
    """

    def __init__(
        self,
        message: str,
        *,
        safe_message: str = "Ресурс уже существует",
    ) -> None:
        super().__init__(message)
        self.safe_message = safe_message


class ValidationError(DomainError):
    """Бизнес-данные не прошли доменную проверку."""

    def __init__(
        self,
        message: str = "Проверка данных не пройдена",
        detail: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.detail = detail or []


class LimitExceeded(DomainError):
    """Операция невозможна из-за превышения установленного лимита"""
