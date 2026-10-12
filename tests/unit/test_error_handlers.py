"""Единое тело ошибок; PermissionDenied неотличим от NotFound (docs/02 механизм 4)."""

import json

from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

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
from app.core.user_context import get_current_user
from app.interface.api.app import create_app
from app.interface.api.exception_handlers import (
    authentication_failed_handler,
    conflict_handler,
    domain_validation_error_handler,
    error_body,
    limit_exceeded_handler,
    not_found_handler,
    permission_denied_handler,
    validation_error_handler,
)

NOT_FOUND_BODY = error_body("NOT_FOUND", "Объект не найден")


async def test_not_found_handler_returns_404() -> None:
    response = await not_found_handler(
        None,
        NotFound("Category не найден"),
    )

    assert response.status_code == 404
    assert json.loads(response.body) == NOT_FOUND_BODY


async def test_permission_denied_handler_is_indistinguishable() -> None:
    response = await permission_denied_handler(
        None,
        PermissionDenied("нет контекста пользователя"),
    )

    assert response.status_code == 404
    assert json.loads(response.body) == NOT_FOUND_BODY


async def test_validation_error_handler_returns_422_with_fields() -> None:
    error = RequestValidationError(
        [
            {
                "loc": ("body", "name"),
                "msg": "Field required",
                "type": "missing",
            }
        ],
        body=None,
    )

    response = await validation_error_handler(None, error)
    body = json.loads(response.body)

    assert response.status_code == 422
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["detail"] == [
        {
            "field": "name",
            "issue": "Field required",
        }
    ]


def test_permission_denied_returns_404_over_http() -> None:
    application = create_app()

    @application.get("/contextless")
    async def contextless() -> None:
        get_current_user()

    client = TestClient(application)
    response = client.get("/contextless")

    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY


async def test_authentication_failed_handler_returns_401() -> None:
    response = await authentication_failed_handler(
        None,
        AuthenticationFailed("неверный токен"),
    )
    body = json.loads(response.body)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert body["error"]["code"] == "UNAUTHORIZED"


async def test_conflict_handler_returns_safe_409() -> None:
    response = await conflict_handler(
        None,
        Conflict("users.email=user@example.com"),
    )
    body = json.loads(response.body)

    assert response.status_code == 409
    assert body == {
        "error": {
            "code": "CONFLICT",
            "message": "Email уже занят",
            "detail": [],
        }
    }
    assert "user@example.com" not in response.body.decode()


async def test_domain_validation_error_returns_422() -> None:
    error = DomainValidationError(
        "Внутреннее правило расчёта",
        detail=[
            {
                "field": "amount",
                "issue": "Сумма должна быть больше нуля",
            }
        ],
    )

    response = await domain_validation_error_handler(None, error)
    body = json.loads(response.body)

    assert response.status_code == 422
    assert body == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Проверка данных не пройдена",
            "detail": [
                {
                    "field": "amount",
                    "issue": "Сумма должна быть больше нуля",
                }
            ],
        }
    }
    assert "Внутреннее правило" not in response.body.decode()


async def test_limit_exceeded_returns_safe_409() -> None:
    response = await limit_exceeded_handler(
        None,
        LimitExceeded("Лимит пользователя 42 равен 1000"),
    )
    body = json.loads(response.body)

    assert response.status_code == 409
    assert body == {
        "error": {
            "code": "LIMIT_EXCEEDED",
            "message": "Установленный лимит превышен",
            "detail": [],
        }
    }
    assert "пользователя 42" not in response.body.decode()
