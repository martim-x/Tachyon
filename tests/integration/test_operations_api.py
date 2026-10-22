"""Сквозные тесты CRUD операций: изоляция, пагинация, фильтры, деньги (docs/03 §S3.2)."""

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.ledger.models import Operation
from tests.conftest import ApiClientFactory, CategoryFactory, UserFactory

pytestmark = pytest.mark.integration


async def create_operation(
    client: AsyncClient,
    category_id: UUID,
    *,
    amount: str = "25.50",
    kind: str = "expense",
    occurred_at: str | None = None,
    note: str | None = None,
) -> dict:
    """POST /operations залогиненным клиентом: токен уже в заголовках клиента."""
    payload: dict = {"category_id": str(category_id), "amount": amount, "kind": kind}
    if occurred_at is not None:
        payload["occurred_at"] = occurred_at
    if note is not None:
        payload["note"] = note
    response = await client.post("/api/v1/operations", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def test_operations_create_returns_all_fields(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    alice, alice_token = await user_factory("alice@test.io")
    client = api_client(token=alice_token)
    category = await category_factory(alice)

    body = await create_operation(
        client,
        category.id,
        occurred_at="2026-10-05T10:00:00Z",
        note="Продукты на неделю",
    )

    assert body["user_id"] == str(alice.id)
    assert body["category_id"] == str(category.id)
    assert body["amount"] == "25.50"
    assert body["kind"] == "expense"
    assert body["occurred_at"].startswith("2026-10-05T10:00:00")
    assert body["note"] == "Продукты на неделю"
    assert body["source"] == "manual"


@pytest.mark.parametrize("amount", [0, "0.00", "-1.00"])
async def test_operations_reject_non_positive_amount(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
    amount,
) -> None:
    alice, alice_token = await user_factory("alice@test.io")
    client = api_client(token=alice_token)
    category = await category_factory(alice)

    response = await client.post(
        "/api/v1/operations",
        json={"category_id": str(category.id), "amount": amount, "kind": "expense"},
    )

    assert response.status_code == 422


async def test_operations_reject_invalid_kind(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    alice, alice_token = await user_factory("alice@test.io")
    client = api_client(token=alice_token)
    category = await category_factory(alice)

    response = await client.post(
        "/api/v1/operations",
        json={"category_id": str(category.id), "amount": "25.50", "kind": "transfer"},
    )

    assert response.status_code == 422


async def test_operations_reject_note_longer_than_500(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    alice, alice_token = await user_factory("alice@test.io")
    client = api_client(token=alice_token)
    category = await category_factory(alice)

    response = await client.post(
        "/api/v1/operations",
        json={
            "category_id": str(category.id),
            "amount": "25.50",
            "kind": "expense",
            "note": "х" * 501,
        },
    )

    assert response.status_code == 422


async def test_operations_accept_note_of_500_chars(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    alice, alice_token = await user_factory("alice@test.io")
    client = api_client(token=alice_token)
    category = await category_factory(alice)

    response = await client.post(
        "/api/v1/operations",
        json={
            "category_id": str(category.id),
            "amount": "25.50",
            "kind": "expense",
            "note": "х" * 500,
        },
    )

    assert response.status_code == 201
    assert len(response.json()["note"]) == 500


async def test_operations_foreign_category_isolation(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    alice, alice_token = await user_factory("alice@test.io")
    _, bob_token = await user_factory("bob@test.io")
    alice_client = api_client(token=alice_token)
    bob_client = api_client(token=bob_token)
    category = await category_factory(alice)

    response = await bob_client.post(
        "/api/v1/operations",
        json={"category_id": str(category.id), "amount": "25.50", "kind": "expense"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    bob_list = (await bob_client.get("/api/v1/operations")).json()
    alice_list = (await alice_client.get("/api/v1/operations")).json()
    assert bob_list["total"] == 0
    assert alice_list["total"] == 0


async def test_operations_list_only_own_sorted_desc(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    alice, alice_token = await user_factory("alice@test.io")
    bob, bob_token = await user_factory("bob@test.io")
    alice_client = api_client(token=alice_token)
    bob_client = api_client(token=bob_token)
    alice_category = await category_factory(alice)
    await create_operation(
        alice_client, alice_category.id, occurred_at="2026-10-05T10:00:00Z", amount="10.00"
    )
    await create_operation(
        alice_client, alice_category.id, occurred_at="2026-10-01T10:00:00Z", amount="20.00"
    )
    bob_category = await category_factory(bob, name="У Боба")
    await create_operation(
        bob_client, bob_category.id, occurred_at="2026-10-03T10:00:00Z", amount="30.00"
    )

    body = (await alice_client.get("/api/v1/operations")).json()
    assert body["total"] == 2
    assert [item["occurred_at"][:10] for item in body["items"]] == ["2026-10-05", "2026-10-01"]

    bob_list = (await bob_client.get("/api/v1/operations")).json()
    assert bob_list["total"] == 1
    assert bob_list["items"][0]["user_id"] == str(bob.id)


async def test_operations_pagination_second_page_with_total(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    alice, alice_token = await user_factory("alice@test.io")
    client = api_client(token=alice_token)
    category = await category_factory(alice)
    for day in range(1, 13):
        await create_operation(
            client,
            category.id,
            occurred_at=f"2026-10-{day:02d}T12:00:00Z",
            amount=f"{day}.00",
        )

    body = (
        await client.get(
            "/api/v1/operations",
            params={"page": 2, "limit": 5},
        )
    ).json()
    assert body["page"] == 2
    assert body["limit"] == 5
    assert body["total"] == 12
    assert [item["occurred_at"][:10] for item in body["items"]] == [
        f"2026-10-{day:02d}" for day in range(7, 2, -1)
    ]

    tail = (
        await client.get(
            "/api/v1/operations",
            params={"page": 3, "limit": 5},
        )
    ).json()
    assert [item["occurred_at"][:10] for item in tail["items"]] == ["2026-10-02", "2026-10-01"]


async def test_operations_filters_period_category_and_kind(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    alice, alice_token = await user_factory("alice@test.io")
    client = api_client(token=alice_token)
    groceries = await category_factory(alice, name="Продукты")
    salary = await category_factory(alice, name="Зарплата")
    oct_expense = await create_operation(
        client, groceries.id, occurred_at="2026-10-05T10:00:00Z", amount="10.00"
    )
    oct_income = await create_operation(
        client,
        salary.id,
        occurred_at="2026-10-20T10:00:00Z",
        amount="50.00",
        kind="income",
    )
    await create_operation(client, groceries.id, occurred_at="2026-09-15T10:00:00Z", amount="5.00")

    period = (
        await client.get(
            "/api/v1/operations",
            params={"from": "2026-10-01", "to": "2026-10-31"},
        )
    ).json()
    assert period["total"] == 2
    assert {item["id"] for item in period["items"]} == {oct_expense["id"], oct_income["id"]}

    income_only = (
        await client.get(
            "/api/v1/operations",
            params={"from": "2026-10-01", "to": "2026-10-31", "type": "income"},
        )
    ).json()
    assert income_only["total"] == 1
    assert income_only["items"][0]["id"] == oct_income["id"]

    by_category = (
        await client.get(
            "/api/v1/operations",
            params={"from": "2026-10-01", "category_id": str(groceries.id)},
        )
    ).json()
    assert by_category["total"] == 1
    assert by_category["items"][0]["id"] == oct_expense["id"]

    empty_period = (
        await client.get(
            "/api/v1/operations",
            params={"from": "2026-11-01"},
        )
    ).json()
    assert empty_period["total"] == 0


async def test_operations_reject_broken_period_and_date_format(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
) -> None:
    _, alice_token = await user_factory("alice@test.io")
    client = api_client(token=alice_token)

    unordered = await client.get(
        "/api/v1/operations",
        params={"from": "2026-10-31", "to": "2026-10-01"},
    )
    assert unordered.status_code == 422

    unparsable = await client.get(
        "/api/v1/operations",
        params={"from": "не-дата"},
    )
    assert unparsable.status_code == 422


async def test_operations_patch_updates_amount_and_note(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
    db_session: async_sessionmaker[AsyncSession],
) -> None:
    alice, alice_token = await user_factory("alice@test.io")
    client = api_client(token=alice_token)
    category = await category_factory(alice)
    created = await create_operation(client, category.id, occurred_at="2026-10-05T10:00:00Z")

    body = (
        await client.patch(
            f"/api/v1/operations/{created['id']}",
            json={"amount": "30.00", "note": "обновлено"},
        )
    ).json()

    assert body["amount"] == "30.00"
    assert body["note"] == "обновлено"
    assert body["kind"] == "expense"

    async with db_session() as session:
        row = await session.get(Operation, UUID(created["id"]))
        assert row is not None
        assert row.amount_cents == 3000


async def test_operations_patch_rejects_null_for_not_null_fields(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    alice, alice_token = await user_factory("alice@test.io")
    client = api_client(token=alice_token)
    category = await category_factory(alice)
    created = await create_operation(client, category.id)

    response = await client.patch(
        f"/api/v1/operations/{created['id']}",
        json={"kind": None},
    )

    assert response.status_code == 422


async def test_operations_patch_rejects_null_amount(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    """PATCH {"amount": null} -> 422: amount_cents тоже NOT NULL, тихий no-op недопустим."""
    alice, alice_token = await user_factory("alice@test.io")
    client = api_client(token=alice_token)
    category = await category_factory(alice)
    created = await create_operation(client, category.id)

    response = await client.patch(
        f"/api/v1/operations/{created['id']}",
        json={"amount": None},
    )

    assert response.status_code == 422


async def test_operations_reject_naive_occurred_at(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    """occurred_at без таймзоны -> 422: в БД метки с таймзоной, naive даёт 500 на PG."""
    alice, alice_token = await user_factory("alice@test.io")
    client = api_client(token=alice_token)
    category = await category_factory(alice)

    response = await client.post(
        "/api/v1/operations",
        json={
            "category_id": str(category.id),
            "amount": "25.50",
            "kind": "expense",
            "occurred_at": "2026-10-05T10:00:00",
        },
    )

    assert response.status_code == 422


async def test_operations_normalize_occurred_at_offset_to_utc(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    """Не-UTC смещение валидно, но хранится и возвращается в UTC (+03:00 -> 10:00 UTC)."""
    alice, alice_token = await user_factory("alice@test.io")
    client = api_client(token=alice_token)
    category = await category_factory(alice)

    created = await create_operation(client, category.id, occurred_at="2026-10-05T13:00:00+03:00")

    assert created["occurred_at"].startswith("2026-10-05T10:00:00")


async def test_operations_reject_amount_over_integer_cents(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    """10 000 000.00 -> 422: схема выровнена под int32 копеек, а не падает на вставке."""
    alice, alice_token = await user_factory("alice@test.io")
    client = api_client(token=alice_token)
    category = await category_factory(alice)

    response = await client.post(
        "/api/v1/operations",
        json={
            "category_id": str(category.id),
            "amount": "10000000.00",
            "kind": "expense",
        },
    )

    assert response.status_code == 422


async def test_operations_patch_foreign_returns_404_isolation(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    """PATCH чужой операции -> 404; данные владельца не меняются."""
    alice, alice_token = await user_factory("alice@test.io")
    _, bob_token = await user_factory("bob@test.io")
    alice_client = api_client(token=alice_token)
    bob_client = api_client(token=bob_token)
    category = await category_factory(alice)
    created = await create_operation(alice_client, category.id)

    response = await bob_client.patch(
        f"/api/v1/operations/{created['id']}",
        json={"note": "взломано"},
    )
    assert response.status_code == 404

    untouched = (await alice_client.get(f"/api/v1/operations/{created['id']}")).json()
    assert untouched["note"] != "взломано"


async def test_operations_patch_foreign_category_isolation(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    alice, _ = await user_factory("alice@test.io")
    bob, bob_token = await user_factory("bob@test.io")
    bob_client = api_client(token=bob_token)
    foreign_category = await category_factory(alice)
    own_category = await category_factory(bob, name="У Боба")
    created = await create_operation(bob_client, own_category.id)

    response = await bob_client.patch(
        f"/api/v1/operations/{created['id']}",
        json={"category_id": str(foreign_category.id)},
    )
    assert response.status_code == 404

    untouched = (await bob_client.get(f"/api/v1/operations/{created['id']}")).json()
    assert untouched["category_id"] == str(own_category.id)


async def test_operations_delete_own_removes(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    alice, alice_token = await user_factory("alice@test.io")
    client = api_client(token=alice_token)
    category = await category_factory(alice)
    created = await create_operation(client, category.id)

    resp = await client.delete(f"/api/v1/operations/{created['id']}")
    assert resp.status_code == 204

    assert (await client.get(f"/api/v1/operations/{created['id']}")).status_code == 404
    listing = (await client.get("/api/v1/operations")).json()
    assert listing["total"] == 0


async def test_operations_delete_foreign_returns_404_isolation(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
) -> None:
    alice, alice_token = await user_factory("alice@test.io")
    _, bob_token = await user_factory("bob@test.io")
    alice_client = api_client(token=alice_token)
    bob_client = api_client(token=bob_token)
    category = await category_factory(alice)
    created = await create_operation(alice_client, category.id)

    response = await bob_client.delete(f"/api/v1/operations/{created['id']}")
    assert response.status_code == 404

    kept = await alice_client.get(f"/api/v1/operations/{created['id']}")
    assert kept.status_code == 200


async def test_operations_empty_list_returns_zero_total(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
) -> None:
    _, alice_token = await user_factory("alice@test.io")
    client = api_client(token=alice_token)

    body = (await client.get("/api/v1/operations")).json()
    assert body == {"items": [], "total": 0, "page": 1, "limit": 20}

    categories = (await client.get("/api/v1/categories")).json()
    assert categories == []


async def test_categories_duplicate_name_returns_conflict(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
) -> None:
    """Повтор имени категории у того же пользователя — 409, а не 500 (ix_categories_user_name)."""
    _, alice_token = await user_factory("alice@test.io")
    client = api_client(token=alice_token)
    payload = {"name": "Продукты", "kind": "expense"}

    first = await client.post("/api/v1/categories", json=payload)
    assert first.status_code == 201, first.text

    second = await client.post("/api/v1/categories", json=payload)
    assert second.status_code == 409, second.text
    body = second.json()
    assert body["error"]["code"] == "CONFLICT"
    assert body["error"]["message"] == "Категория с таким именем уже существует"

    # Сессия после отката рабочая: список по-прежнему отдаёт ровно одну категорию.
    listed = await client.get("/api/v1/categories")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


async def test_operations_require_authentication(api_client: ApiClientFactory) -> None:
    client = api_client()
    assert (await client.get("/api/v1/operations")).status_code == 401
    assert (await client.post("/api/v1/operations", json={})).status_code == 401
    assert (await client.get("/api/v1/categories")).status_code == 401
