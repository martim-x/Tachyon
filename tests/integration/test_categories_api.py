"""Сквозные тесты CRUD категорий: изоляция, имя, запрет удаления (docs/03 §S3.1)."""

from uuid import uuid4

import pytest
from httpx import AsyncClient, Response

from tests.conftest import ApiClientFactory, CategoryFactory, OperationFactory, UserFactory

pytestmark = pytest.mark.integration

DUPLICATE_MESSAGE = "Категория с таким именем уже существует"
IN_USE_MESSAGE = "Нельзя удалить категорию, пока на неё ссылаются операции"
NOT_FOUND_BODY = {
    "error": {
        "code": "NOT_FOUND",
        "message": "Объект не найден",
        "detail": [],
    }
}


def _assert_field_error(response: Response, field: str) -> None:
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert any(item["field"] == field for item in body["error"]["detail"])


async def test_create_category_stores_caller_user_id(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
) -> None:
    alice, alice_token = await user_factory("alice@test.io")
    bob, _bob_token = await user_factory("bob@test.io")
    client = api_client(token=alice_token)

    response = await client.post(
        "/api/v1/categories",
        json={"name": "Продукты", "kind": "expense", "user_id": str(bob.id)},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Продукты"
    assert body["kind"] == "expense"
    assert body["user_id"] == str(alice.id)
    assert body["user_id"] != str(bob.id)


async def test_create_strips_name(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
) -> None:
    _, token = await user_factory("alice@test.io")
    client = api_client(token=token)

    response = await client.post(
        "/api/v1/categories",
        json={"name": "  Продукты  ", "kind": "expense"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["name"] == "Продукты"


async def test_duplicate_name_for_same_user_returns_409(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
) -> None:
    _, token = await user_factory("alice@test.io")
    client = api_client(token=token)
    payload = {"name": "Продукты", "kind": "expense"}

    first = await client.post("/api/v1/categories", json=payload)
    assert first.status_code == 201, first.text

    second = await client.post("/api/v1/categories", json=payload)
    assert second.status_code == 409, second.text
    body = second.json()
    assert body["error"]["code"] == "CONFLICT"
    assert body["error"]["message"] == DUPLICATE_MESSAGE

    listed = await client.get("/api/v1/categories")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


async def test_same_name_allowed_for_different_users(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
) -> None:
    alice, alice_token = await user_factory("alice@test.io")
    bob, bob_token = await user_factory("bob@test.io")
    payload = {"name": "Продукты", "kind": "expense"}

    first = await api_client(token=alice_token).post("/api/v1/categories", json=payload)
    second = await api_client(token=bob_token).post("/api/v1/categories", json=payload)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["user_id"] == str(alice.id)
    assert second.json()["user_id"] == str(bob.id)
    assert first.json()["id"] != second.json()["id"]


@pytest.mark.parametrize("name", ["", "   ", "я" * 51])
async def test_create_rejects_empty_or_too_long_name(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    name: str,
) -> None:
    _, token = await user_factory("alice@test.io")
    client = api_client(token=token)

    response = await client.post(
        "/api/v1/categories",
        json={"name": name, "kind": "expense"},
    )

    _assert_field_error(response, "name")


async def test_create_accepts_name_of_50_chars(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
) -> None:
    _, token = await user_factory("alice@test.io")
    client = api_client(token=token)
    name = "я" * 50

    response = await client.post(
        "/api/v1/categories",
        json={"name": name, "kind": "expense"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["name"] == name


async def test_create_rejects_invalid_kind(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
) -> None:
    _, token = await user_factory("alice@test.io")
    client = api_client(token=token)

    response = await client.post(
        "/api/v1/categories",
        json={"name": "Продукты", "kind": "transfer"},
    )

    _assert_field_error(response, "kind")


async def test_list_empty_is_200(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
) -> None:
    _, token = await user_factory("alice@test.io")
    client = api_client(token=token)

    response = await client.get("/api/v1/categories")

    assert response.status_code == 200
    assert response.json() == []


async def test_list_returns_only_own_and_ignores_foreign_user_id(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    alice, alice_token = await user_factory("alice@test.io")
    bob, bob_token = await user_factory("bob@test.io")
    own = await category_factory(alice, name="Своя")
    foreign = await category_factory(bob, name="Чужая")
    alice_client = api_client(token=alice_token)

    response = await alice_client.get(
        "/api/v1/categories",
        params={"user_id": str(bob.id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [str(own.id)]
    assert all(item["user_id"] == str(alice.id) for item in body)

    bob_list = (await api_client(token=bob_token).get("/api/v1/categories")).json()
    assert [item["id"] for item in bob_list] == [str(foreign.id)]


async def test_get_own_category(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    alice, token = await user_factory("alice@test.io")
    client = api_client(token=token)
    category = await category_factory(alice, name="Продукты")

    response = await client.get(f"/api/v1/categories/{category.id}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(category.id)
    assert body["user_id"] == str(alice.id)
    assert body["name"] == "Продукты"


async def test_get_foreign_and_missing_are_identical_404(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    alice, _alice_token = await user_factory("alice@test.io")
    _, bob_token = await user_factory("bob@test.io")
    bob = api_client(token=bob_token)
    category = await category_factory(alice, name="Продукты")

    foreign = await bob.get(f"/api/v1/categories/{category.id}")
    missing = await bob.get(f"/api/v1/categories/{uuid4()}")

    assert foreign.status_code == 404
    assert missing.status_code == 404
    assert foreign.json() == NOT_FOUND_BODY
    assert missing.json() == NOT_FOUND_BODY


async def test_patch_renames_and_keeps_user_id(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    alice, token = await user_factory("alice@test.io")
    client = api_client(token=token)
    category = await category_factory(alice, name="Продукты")

    response = await client.patch(
        f"/api/v1/categories/{category.id}",
        json={"name": "Транспорт"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(category.id)
    assert body["name"] == "Транспорт"
    assert body["user_id"] == str(alice.id)


async def test_patch_foreign_returns_404_and_keeps_name(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    alice, alice_token = await user_factory("alice@test.io")
    _, bob_token = await user_factory("bob@test.io")
    category = await category_factory(alice, name="Продукты")

    response = await api_client(token=bob_token).patch(
        f"/api/v1/categories/{category.id}",
        json={"name": "Взлом"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    kept = await api_client(token=alice_token).get(f"/api/v1/categories/{category.id}")
    assert kept.status_code == 200
    assert kept.json()["name"] == "Продукты"


async def test_patch_duplicate_name_returns_409(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    alice, token = await user_factory("alice@test.io")
    client = api_client(token=token)
    category = await category_factory(alice, name="Продукты")
    await category_factory(alice, name="Транспорт")

    response = await client.patch(
        f"/api/v1/categories/{category.id}",
        json={"name": "Транспорт"},
    )

    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "CONFLICT"
    assert response.json()["error"]["message"] == DUPLICATE_MESSAGE
    kept = await client.get(f"/api/v1/categories/{category.id}")
    assert kept.json()["name"] == "Продукты"


@pytest.mark.parametrize("name", ["", "   ", "я" * 51])
async def test_patch_rejects_empty_or_too_long_name(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
    name: str,
) -> None:
    alice, token = await user_factory("alice@test.io")
    client = api_client(token=token)
    category = await category_factory(alice, name="Продукты")

    response = await client.patch(
        f"/api/v1/categories/{category.id}",
        json={"name": name},
    )

    _assert_field_error(response, "name")


async def test_patch_rejects_null_name(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    alice, token = await user_factory("alice@test.io")
    client = api_client(token=token)
    category = await category_factory(alice, name="Продукты")

    response = await client.patch(
        f"/api/v1/categories/{category.id}",
        json={"name": None},
    )

    assert response.status_code == 422, response.text


async def test_delete_without_operations(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    alice, token = await user_factory("alice@test.io")
    client = api_client(token=token)
    category = await category_factory(alice, name="Продукты")

    response = await client.delete(f"/api/v1/categories/{category.id}")

    assert response.status_code == 204
    assert response.content == b""
    assert (await client.get(f"/api/v1/categories/{category.id}")).status_code == 404
    assert (await client.get("/api/v1/categories")).json() == []


async def test_delete_with_operations_is_forbidden(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
    operation_factory: OperationFactory,
) -> None:
    alice, token = await user_factory("alice@test.io")
    client = api_client(token=token)
    category = await category_factory(alice, name="Продукты")
    operation = await operation_factory(alice, category=category)

    response = await client.delete(f"/api/v1/categories/{category.id}")

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error"]["code"] == "CONFLICT"
    assert body["error"]["message"] == IN_USE_MESSAGE
    assert (await client.get(f"/api/v1/categories/{category.id}")).status_code == 200
    assert (await client.get(f"/api/v1/operations/{operation.id}")).status_code == 200


async def test_delete_foreign_returns_404_and_keeps_category(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    alice, alice_token = await user_factory("alice@test.io")
    _, bob_token = await user_factory("bob@test.io")
    category = await category_factory(alice, name="Продукты")

    response = await api_client(token=bob_token).delete(f"/api/v1/categories/{category.id}")

    assert response.status_code == 404
    assert response.json() == NOT_FOUND_BODY
    kept = await api_client(token=alice_token).get(f"/api/v1/categories/{category.id}")
    assert kept.status_code == 200
    assert kept.json()["name"] == "Продукты"


async def test_categories_require_authentication(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    alice, _token = await user_factory("alice@test.io")
    category = await category_factory(alice, name="Продукты")
    client: AsyncClient = api_client()

    assert (await client.get("/api/v1/categories")).status_code == 401
    assert (await client.get(f"/api/v1/categories/{category.id}")).status_code == 401
    assert (
        await client.post("/api/v1/categories", json={"name": "X", "kind": "expense"})
    ).status_code == 401
    assert (
        await client.patch(f"/api/v1/categories/{category.id}", json={"name": "Y"})
    ).status_code == 401
    assert (await client.delete(f"/api/v1/categories/{category.id}")).status_code == 401
