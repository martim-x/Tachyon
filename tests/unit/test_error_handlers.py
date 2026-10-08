"""Единое тело ошибок; PermissionDenied неотличим от NotFound (docs/02 механизм 4)."""

import json

from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

from app.core.errors import NotFound, PermissionDenied
from app.core.user_context import get_current_user
from app.interface.api.app import create_app
from app.interface.api.exception_handlers import (
    error_body,
    not_found_handler,
    permission_denied_handler,
    validation_error_handler,
)

NOT_FOUND_BODY = error_body("NOT_FOUND", "Объект не найден")


async def test_not_found_handler_returns_404() -> None:
    response = await not_found_handler(None, NotFound("Category не найден"))

    assert response.status_code == 404
    assert json.loads(response.body) == NOT_FOUND_BODY


async def test_permission_denied_handler_is_indistinguishable() -> None:
    response = await permission_denied_handler(None, PermissionDenied("нет контекста пользователя"))

    assert response.status_code == 404
    assert json.loads(response.body) == NOT_FOUND_BODY


async def test_validation_error_handler_returns_422_with_fields() -> None:
    error = RequestValidationError(
        [{"loc": ("body", "name"), "msg": "Field required", "type": "missing"}],
        body=None,
    )
    response = await validation_error_handler(None, error)

    assert response.status_code == 422
    body = json.loads(response.body)
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["detail"] == [{"field": "name", "issue": "Field required"}]


def test_permission_denied_returns_404_over_http() -> None:
    application = create_app()

    @application.get("/contextless")
    async def contextless() -> None:
        get_current_user()

    client = TestClient(application)
    response = client.get("/contextless")

    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY