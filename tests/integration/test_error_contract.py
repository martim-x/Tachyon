"""Интеграционные тесты единого контракта ошибок API."""

from uuid import uuid4

import pytest

from tests.conftest import ApiClientFactory, CategoryFactory, LoggedInClient, OperationFactory

pytestmark = pytest.mark.integration


async def test_validation_error_has_unified_contract(
    api_client_a: LoggedInClient,
    category_factory: CategoryFactory,
) -> None:
    category = await category_factory(api_client_a.user)

    response = await api_client_a.client.post(
        "/api/v1/operations",
        json={
            "category_id": str(category.id),
            "amount": "0.00",
            "kind": "expense",
        },
    )

    assert response.status_code == 422

    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["message"] == "Проверка данных не пройдена"
    assert isinstance(body["error"]["detail"], list)
    assert any(item["field"] == "amount" for item in body["error"]["detail"])


async def test_foreign_and_missing_objects_have_identical_404(
    api_client_a: LoggedInClient,
    api_client_b: LoggedInClient,
    operation_factory: OperationFactory,
) -> None:
    alice_operation = await operation_factory(api_client_a.user)

    foreign_response = await api_client_b.client.get(f"/api/v1/operations/{alice_operation.id}")
    missing_response = await api_client_b.client.get(f"/api/v1/operations/{uuid4()}")

    expected_body = {
        "error": {
            "code": "NOT_FOUND",
            "message": "Объект не найден",
            "detail": [],
        }
    }

    assert foreign_response.status_code == 404
    assert missing_response.status_code == 404
    assert foreign_response.json() == expected_body
    assert missing_response.json() == expected_body


async def test_missing_token_has_unified_contract(
    api_client: ApiClientFactory,
) -> None:
    response = await api_client().get("/api/v1/operations")

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "UNAUTHORIZED",
            "message": "Не удалось подтвердить учётные данные",
            "detail": [],
        }
    }


async def test_empty_user_receives_zero_values(
    api_client_a: LoggedInClient,
) -> None:
    operations_response = await api_client_a.client.get("/api/v1/operations")
    categories_response = await api_client_a.client.get("/api/v1/categories")

    assert operations_response.status_code == 200
    assert operations_response.json() == {
        "items": [],
        "total": 0,
        "page": 1,
        "limit": 20,
    }

    assert categories_response.status_code == 200
    assert categories_response.json() == []
