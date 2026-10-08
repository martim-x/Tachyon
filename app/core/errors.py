"""Доменные исключения проекта (docs/02: errors.py объявляет NotFound и PermissionDenied)."""


class DomainError(Exception):
    """Базовое исключение домена с сообщением для человека."""


class NotFound(DomainError):
    """Объект не найден или принадлежит другому пользователю."""


class PermissionDenied(DomainError):
    """Действие запрещено: например, нет контекста пользователя."""