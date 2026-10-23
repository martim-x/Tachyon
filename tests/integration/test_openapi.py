"""Контракт опубликованной OpenAPI-спецификации."""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.interface.api.app import create_app

pytestmark = pytest.mark.integration

HTTP_METHODS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
}

EXPECTED_TAGS = {
    "Авторизация",
    "Операции",
    "Категории",
    "Бюджет",
    "Повторяющиеся операции",
    "Отчёты",
    "Прогноз",
    "Система",
}

EXPECTED_API_ROUTES = {
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/login"),
    ("GET", "/api/v1/auth/me"),
    ("POST", "/api/v1/operations"),
    ("GET", "/api/v1/operations"),
    ("GET", "/api/v1/operations/{operation_id}"),
    ("PATCH", "/api/v1/operations/{operation_id}"),
    ("DELETE", "/api/v1/operations/{operation_id}"),
    ("GET", "/api/v1/categories"),
    ("POST", "/api/v1/categories"),
    ("GET", "/api/v1/categories/{category_id}"),
    ("PATCH", "/api/v1/categories/{category_id}"),
    ("DELETE", "/api/v1/categories/{category_id}"),
    ("GET", "/api/v1/budget-limits"),
    ("POST", "/api/v1/budget-limits"),
    ("PUT", "/api/v1/budget-limits/{category_id}"),
    ("GET", "/api/v1/budget-limits/status"),
    ("GET", "/api/v1/recurring/rules"),
    ("POST", "/api/v1/recurring/rules"),
    ("GET", "/api/v1/recurring/rules/{rule_id}"),
    ("PATCH", "/api/v1/recurring/rules/{rule_id}"),
    ("DELETE", "/api/v1/recurring/rules/{rule_id}"),
    ("POST", "/api/v1/recurring/rules/run"),
    ("GET", "/api/v1/reports/monthly"),
    ("GET", "/api/v1/reports/by-category"),
    ("GET", "/api/v1/reports/monthly/export"),
    ("GET", "/api/v1/forecast"),
}

OPENAPI_PATH = Path(__file__).resolve().parents[2] / "openapi.json"


def openapi_schema() -> dict[str, Any]:
    """Сгенерировать спецификацию непосредственно из приложения."""

    return create_app().openapi()


def documented_routes(
    schema: dict[str, Any],
) -> set[tuple[str, str]]:
    """Получить пары HTTP-метод и путь из OpenAPI."""

    routes: set[tuple[str, str]] = set()

    for path, path_data in schema["paths"].items():
        for method in path_data:
            if method.lower() in HTTP_METHODS:
                routes.add(
                    (
                        method.upper(),
                        path,
                    )
                )

    return routes


def api_operations(
    schema: dict[str, Any],
):
    """Перебрать все операции публичного API v1."""

    for path, path_data in schema["paths"].items():
        if not path.startswith("/api/v1"):
            continue

        for method, operation in path_data.items():
            if method.lower() in HTTP_METHODS:
                yield (
                    method.upper(),
                    path,
                    operation,
                )


def test_exported_openapi_matches_generated_schema() -> None:
    exported_schema = json.loads(
        OPENAPI_PATH.read_text(
            encoding="utf-8",
        )
    )

    assert exported_schema == openapi_schema()


def test_openapi_contains_all_required_routes() -> None:
    schema = openapi_schema()
    actual_routes = documented_routes(schema)

    missing_routes = EXPECTED_API_ROUTES - actual_routes

    assert not missing_routes, f"В OpenAPI отсутствуют маршруты: {sorted(missing_routes)}"


def test_openapi_declares_all_domain_tags() -> None:
    schema = openapi_schema()
    declared_tags = {tag["name"] for tag in schema["tags"]}

    assert EXPECTED_TAGS <= declared_tags

    for tag in schema["tags"]:
        if tag["name"] in EXPECTED_TAGS:
            assert tag["description"]


def test_every_api_operation_has_metadata() -> None:
    schema = openapi_schema()

    for method, path, operation in api_operations(schema):
        message = f"{method} {path}"

        assert operation.get("tags"), f"{message}: отсутствует тег"
        assert operation.get("summary"), f"{message}: отсутствует summary"
        assert operation.get("description"), f"{message}: отсутствует description"


def test_every_api_operation_has_success_response_schema() -> None:
    schema = openapi_schema()

    for method, path, operation in api_operations(schema):
        message = f"{method} {path}"
        responses = operation["responses"]

        success_codes = [code for code in responses if code.startswith("2")]

        assert success_codes, f"{message}: не объявлен успешный ответ"

        for code in success_codes:
            if code == "204":
                continue

            response = responses[code]
            content = response.get("content")

            assert content, f"{message}: ответ {code} не содержит content"

            assert any(media.get("schema") for media in content.values()), (
                f"{message}: ответ {code} не содержит схему"
            )


def test_documented_errors_use_common_component() -> None:
    schema = openapi_schema()

    for method, path, operation in api_operations(schema):
        for status_code in (
            "401",
            "404",
            "409",
            "422",
        ):
            response = operation["responses"].get(status_code)

            if response is None:
                continue

            error_schema = response["content"]["application/json"]["schema"]

            assert error_schema["$ref"].endswith("/ErrorResponse"), (
                f"{method} {path}: ошибка {status_code} использует другую схему"
            )


def test_error_response_component_has_expected_shape() -> None:
    schema = openapi_schema()
    components = schema["components"]["schemas"]

    error_schema = components["ErrorResponse"]
    assert set(error_schema["properties"]) == {"error"}

    content_schema = components["ErrorContent"]
    assert set(content_schema["properties"]) == {
        "code",
        "message",
        "detail",
    }

    detail_schema = components["ErrorDetail"]
    assert set(detail_schema["properties"]) == {
        "field",
        "issue",
    }


@pytest.mark.parametrize(
    (
        "path",
        "expected_parameters",
    ),
    [
        (
            "/api/v1/reports/monthly",
            {"from", "to"},
        ),
        (
            "/api/v1/reports/by-category",
            {"from", "to"},
        ),
        (
            "/api/v1/reports/monthly/export",
            {"from", "to", "format"},
        ),
        (
            "/api/v1/forecast",
            {"month", "pace"},
        ),
    ],
)
def test_report_parameters_are_documented(
    path: str,
    expected_parameters: set[str],
) -> None:
    schema = openapi_schema()
    operation = schema["paths"][path]["get"]

    parameters = {parameter["name"]: parameter for parameter in operation["parameters"]}

    assert expected_parameters <= set(parameters)

    for parameter_name in expected_parameters:
        parameter = parameters[parameter_name]

        assert parameter["description"]
        assert parameter["schema"]


def test_actual_422_matches_documented_error_envelope() -> None:
    application = create_app()
    client = TestClient(
        application,
        raise_server_exceptions=False,
    )

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "not-an-email",
            "password": "short",
        },
    )

    assert response.status_code == 422

    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {
        "code",
        "message",
        "detail",
    }
    assert body["error"]["code"] == ("VALIDATION_ERROR")
    assert isinstance(
        body["error"]["detail"],
        list,
    )


def schema_example(
    component: dict[str, Any],
    component_name: str,
) -> dict[str, Any]:
    example = component.get("example")
    examples = component.get("examples")

    assert example is not None or examples, f"{component_name}: отсутствуют example или examples"

    if example is not None:
        return example

    return examples[0]


def test_money_examples_are_strings() -> None:
    schema = openapi_schema()
    components = schema["components"]["schemas"]

    report_example = schema_example(
        components["ReportDTO"],
        "ReportDTO",
    )
    forecast_example = schema_example(
        components["ForecastDTO"],
        "ForecastDTO",
    )

    assert isinstance(
        report_example["income"],
        str,
    )
    assert isinstance(
        report_example["expense"],
        str,
    )
    assert isinstance(
        report_example["balance"],
        str,
    )
    assert isinstance(
        forecast_example["spent_to_date"],
        str,
    )
    assert isinstance(
        forecast_example["daily_rate"],
        str,
    )
    assert isinstance(
        forecast_example["projected_total"],
        str,
    )
