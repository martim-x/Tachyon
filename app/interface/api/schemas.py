"""Общие схемы и OpenAPI-компоненты HTTP API."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ErrorDetail(BaseModel):
    """Описание одного некорректного поля."""

    field: str
    issue: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "field": "amount",
                "issue": "Значение должно быть больше нуля",
            }
        }
    )


class ErrorContent(BaseModel):
    """Машиночитаемое содержимое ошибки."""

    code: str
    message: str
    detail: list[ErrorDetail] = Field(
        default_factory=list,
    )


class ErrorResponse(BaseModel):
    """Единый контракт ошибки API."""

    error: ErrorContent

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": ("Проверка данных не пройдена"),
                    "detail": [
                        {
                            "field": "amount",
                            "issue": ("Значение должно быть больше нуля"),
                        }
                    ],
                }
            }
        }
    )


ERROR_DESCRIPTIONS = {
    401: "Требуется корректная авторизация",
    404: "Объект не найден",
    409: "Конфликт с текущим состоянием данных",
    422: "Ошибка проверки входных данных",
    500: "Внутренняя ошибка сервера",
}


def error_responses(
    *status_codes: int,
) -> dict[int | str, dict[str, Any]]:
    """Сформировать OpenAPI responses с единой ErrorResponse."""

    responses: dict[
        int | str,
        dict[str, Any],
    ] = {}

    for status_code in status_codes:
        responses[status_code] = {
            "model": ErrorResponse,
            "description": ERROR_DESCRIPTIONS[status_code],
        }

    return responses


def error_body(
    code: str,
    message: str,
    detail: list[dict[str, str]] | None = None,
) -> dict:
    """Сформировать единственное тело ошибки для всего API."""

    response = ErrorResponse.model_validate(
        {
            "error": {
                "code": code,
                "message": message,
                "detail": detail or [],
            }
        }
    )

    return response.model_dump()
