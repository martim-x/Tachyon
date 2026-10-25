"""Единый контракт ошибок и политика 404 вместо 403.

Паттерн: централизованные обработчики + единый error envelope.
Домены поднимают исключения и не формируют HTTP-ответы самостоятельно.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse

from app.core.errors import (
    AuthenticationFailed,
    Conflict,
    LimitExceeded,
    NotFound,
    PermissionDenied,
)
from app.core.errors import ValidationError as DomainValidationError
from app.interface.api.schemas import error_body


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
    request: Request,
    _exc: AuthenticationFailed,
) -> JSONResponse | RedirectResponse:
    # HTML-страницы дашборда: браузерная сессия (cookie) -> редирект на /login
    # с очисткой старой cookie. JSON API получает стандартный error envelope.
    path = getattr(getattr(request, "url", None), "path", "") or ""
    if path.startswith("/dashboard"):
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie(key="access_token", path="/")
        return response
    return JSONResponse(
        error_body("UNAUTHORIZED", "Не удалось подтвердить учётные данные"),
        status_code=401,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def conflict_handler(_request: Request, exc: Conflict) -> JSONResponse:
    # Текст исключения не отдаём клиенту: он может содержать email или детали БД.
    # Клиенту уходит только safe_message — явно безопасная формулировка домена.
    return JSONResponse(
        error_body("CONFLICT", exc.safe_message),
        status_code=409,
    )


async def domain_validation_error_handler(
    _request: Request,
    exc: DomainValidationError,
) -> JSONResponse:
    # Клиенту доступны только безопасные структурированные сведения о полях.
    return JSONResponse(
        error_body(
            "VALIDATION_ERROR",
            "Проверка данных не пройдена",
            exc.detail,
        ),
        status_code=422,
    )


async def limit_exceeded_handler(
    _request: Request,
    _exc: LimitExceeded,
) -> JSONResponse:
    return JSONResponse(
        error_body(
            "LIMIT_EXCEEDED",
            "Установленный лимит превышен",
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
    """Подключить обработчики к приложению.

    starlette типизирует handler как Callable[[Request, Exception], ...],
    хотя фактически вызывает его только с зарегистрированным классом
    исключения. Обработчики ниже точнее этой сигнатуры, поэтому mypy
    видит несовместимость параметров; каждый ignore[arg-type] покрывает
    ровно один вызов регистрации.
    """
    application.add_exception_handler(NotFound, not_found_handler)  # type: ignore[arg-type]
    application.add_exception_handler(PermissionDenied, permission_denied_handler)  # type: ignore[arg-type]
    application.add_exception_handler(AuthenticationFailed, authentication_failed_handler)  # type: ignore[arg-type]
    application.add_exception_handler(Conflict, conflict_handler)  # type: ignore[arg-type]
    application.add_exception_handler(DomainValidationError, domain_validation_error_handler)  # type: ignore[arg-type]
    application.add_exception_handler(LimitExceeded, limit_exceeded_handler)  # type: ignore[arg-type]
    application.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
