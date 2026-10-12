"""Единый контракт ошибок и политика 404 вместо 403.

Паттерн: централизованные обработчики + единый error envelope.
Домены поднимают исключения и не формируют HTTP-ответы самостоятельно.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.errors import (
    AuthenticationFailed,
    Conflict,
    LimitExceeded,
    NotFound,
    PermissionDenied,
)
from app.core.errors import (
    ValidationError as DomainValidationError,
)
from app.interface.api.schemas import ErrorContent, ErrorResponse


def error_body(
    code: str,
    message: str,
    detail: list[dict[str, str]] | None = None,
) -> dict:
    """Сформировать единственное тело ошибки для всего API."""
    response = ErrorResponse(
        error=ErrorContent(
            code=code,
            message=message,
            detail=detail or [],
        )
    )
    return response.model_dump()


async def not_found_handler(_request: Request, _exc: NotFound) -> JSONResponse:
    return JSONResponse(
        error_body("NOT_FOUND", "Объект не найден"),
        status_code=404,
    )


async def permission_denied_handler(
    _request: Request,
    _exc: PermissionDenied,
) -> JSONResponse:
    # Не подтверждаем существование чужого объекта.
    return JSONResponse(
        error_body("NOT_FOUND", "Объект не найден"),
        status_code=404,
    )


async def authentication_failed_handler(
    _request: Request,
    _exc: AuthenticationFailed,
) -> JSONResponse:
    return JSONResponse(
        error_body("UNAUTHORIZED", "Не удалось подтвердить учётные данные"),
        status_code=401,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def conflict_handler(_request: Request, exc: Conflict) -> JSONResponse:
    return JSONResponse(
        error_body("CONFLICT", str(exc) or "Конфликт данных"),
        status_code=409,
    )


async def domain_validation_error_handler(
    _request: Request,
    exc: DomainValidationError,
) -> JSONResponse:
    return JSONResponse(
        error_body(
            "VALIDATION_ERROR",
            str(exc) or "Проверка данных не пройдена",
            exc.detail,
        ),
        status_code=422,
    )


async def limit_exceeded_handler(
    _request: Request,
    exc: LimitExceeded,
) -> JSONResponse:
    return JSONResponse(
        error_body(
            "LIMIT_EXCEEDED",
            str(exc) or "Установленный лимит превышен",
        ),
        status_code=409,
    )


async def validation_error_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    detail = [
        {
            "field": ".".join(str(part) for part in error["loc"][1:]),
            "issue": error["msg"],
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        error_body(
            "VALIDATION_ERROR",
            "Проверка данных не пройдена",
            detail,
        ),
        status_code=422,
    )


def register_exception_handlers(application: FastAPI) -> None:
    """Подключить обработчики к приложению."""
    application.add_exception_handler(NotFound, not_found_handler)
    application.add_exception_handler(PermissionDenied, permission_denied_handler)
    application.add_exception_handler(AuthenticationFailed, authentication_failed_handler)
    application.add_exception_handler(Conflict, conflict_handler)
    application.add_exception_handler(DomainValidationError, domain_validation_error_handler)
    application.add_exception_handler(LimitExceeded, limit_exceeded_handler)
    application.add_exception_handler(RequestValidationError, validation_error_handler)
