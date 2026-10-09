"""Единое тело ошибок и политика 404 вместо 403 (docs/02 «Изоляция данных», механизм 4).

Паттерн: централизованные обработчики + единый error envelope. 403 «объект
существует, но не твой» подтверждает существование чужих записей; 404
неотличим от ответа на несуществующий UUID, поэтому перебор бесполезен.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.errors import (
    AuthenticationFailed,
    Conflict,
    NotFound,
    PermissionDenied,
)


def error_body(code: str, message: str, detail: list | None = None) -> dict:
    """HTTP-код несёт статус, code - машиночитаемый id, message - текст, detail - поля при 422."""
    return {"error": {"code": code, "message": message, "detail": detail or []}}


async def not_found_handler(_request: Request, _exc: NotFound) -> JSONResponse:
    return JSONResponse(error_body("NOT_FOUND", "Объект не найден"), status_code=404)


async def permission_denied_handler(_request: Request, _exc: PermissionDenied) -> JSONResponse:
    # Тот же код и то же тело, что у NotFound: не подтверждаем существование чужих записей.
    return JSONResponse(error_body("NOT_FOUND", "Объект не найден"), status_code=404)


async def authentication_failed_handler(
    _request: Request,
    _exc: AuthenticationFailed,
) -> JSONResponse:
    # Причина отказа едина для неверного пароля и любого невалидного JWT.
    return JSONResponse(
        error_body("UNAUTHORIZED", "Не удалось подтвердить учётные данные"),
        status_code=401,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def conflict_handler(_request: Request, _exc: Conflict) -> JSONResponse:
    return JSONResponse(
        error_body("CONFLICT", "Email уже занят"),
        status_code=409,
    )


async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    detail = [
        {"field": ".".join(str(part) for part in error["loc"][1:]), "issue": error["msg"]}
        for error in exc.errors()
    ]
    return JSONResponse(
        error_body("VALIDATION_ERROR", "Проверка данных не пройдена", detail),
        status_code=422,
    )


def register_exception_handlers(application: FastAPI) -> None:
    """Подключить обработчики к приложению."""
    application.add_exception_handler(NotFound, not_found_handler)
    application.add_exception_handler(PermissionDenied, permission_denied_handler)
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    application.add_exception_handler(AuthenticationFailed, authentication_failed_handler)
    application.add_exception_handler(Conflict, conflict_handler)
