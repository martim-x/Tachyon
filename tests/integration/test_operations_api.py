"""Сквозные тесты CRUD операций: изоляция, пагинация, фильтры, деньги (docs/03 §S3.2)."""

from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.persistence import Base, get_session, session_scope
from app.domains.ledger.models import Category, Operation
from app.interface.api.app import create_app
from tests.integration import factories


@pytest.fixture
async def db(tmp_path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    database_path = tmp_path / "operations.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


@pytest.fixture
async def client(db) -> AsyncIterator[AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_scope(db) as session:
            yield session

    application = create_app()
    application.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


async def register_and_login(client: AsyncClient, email: str = "alice@test.io") -> tuple[UUID, str]:
    registered = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123"},
    )
    assert registered.status_code == 201, registered.text
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert login.status_code == 200, login.text
    return UUID(registered.json()["id"]), login.json()["access_token"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def seed_category(
    db: async_sessionmaker[AsyncSession],
    user_id: UUID,
    name: str = "Продукты",
) -> Category:
    async with db() as session:
        category = await factories.create_category(session, user_id, name=name)
        await session.commit()
        return category


async def create_operation(
    client: AsyncClient,
    token: str,
    category_id: UUID,
    *,
    amount: str = "25.50",
    kind: str = "expense",
    occurred_at: str | None = None,
    note: str | None = None,
) -> dict:
    payload: dict = {"category_id": str(category_id), "amount": amount, "kind": kind}
    if occurred_at is not None:
        payload["occurred_at"] = occurred_at
    if note is not None:
        payload["note"] = note
    response = await client.post("/api/v1/operations", json=payload, headers=bearer(token))
    assert response.status_code == 201, response.text
    return response.json()


async def test_operations_create_returns_all_fields(client, db) -> None:
    alice_id, alice_token = await register_and_login(client)
    category = await seed_category(db, alice_id)

    body = await create_operation(
        client,
        alice_token,
        category.id,
        occurred_at="2026-10-05T10:00:00Z",
        note="Продукты на неделю",
    )

    assert body["user_id"] == str(alice_id)
    assert body["category_id"] == str(category.id)
    assert body["amount"] == "25.50"
    assert body["kind"] == "expense"
    assert body["occurred_at"].startswith("2026-10-05T10:00:00")
    assert body["note"] == "Продукты на неделю"
    assert body["source"] == "manual"


@pytest.mark.parametrize("amount", [0, "0.00", "-1.00"])
async def test_operations_reject_non_positive_amount(client, db, amount) -> None:
    alice_id, alice_token = await register_and_login(client)
    category = await seed_category(db, alice_id)

    response = await client.post(
        "/api/v1/operations",
        json={"category_id": str(category.id), "amount": amount, "kind": "expense"},
        headers=bearer(alice_token),
    )

    assert response.status_code == 422


async def test_operations_reject_invalid_kind(client, db) -> None:
    alice_id, alice_token = await register_and_login(client)
    category = await seed_category(db, alice_id)

    response = await client.post(
        "/api/v1/operations",
        json={"category_id": str(category.id), "amount": "25.50", "kind": "transfer"},
        headers=bearer(alice_token),
    )

    assert response.status_code == 422


async def test_operations_reject_note_longer_than_500(client, db) -> None:
    alice_id, alice_token = await register_and_login(client)
    category = await seed_category(db, alice_id)

    response = await client.post(
        "/api/v1/operations",
        json={
            "category_id": str(category.id),
            "amount": "25.50",
            "kind": "expense",
            "note": "х" * 501,
        },
        headers=bearer(alice_token),
    )

    assert response.status_code == 422


async def test_operations_accept_note_of_500_chars(client, db) -> None:
    alice_id, alice_token = await register_and_login(client)
    category = await seed_category(db, alice_id)

    response = await client.post(
        "/api/v1/operations",
        json={
            "category_id": str(category.id),
            "amount": "25.50",
            "kind": "expense",
            "note": "х" * 500,
        },
        headers=bearer(alice_token),
    )

    assert response.status_code == 201
    assert len(response.json()["note"]) == 500


async def test_operations_foreign_category_isolation(client, db) -> None:
    alice_id, alice_token = await register_and_login(client, "alice@test.io")
    _, bob_token = await register_and_login(client, "bob@test.io")
    category = await seed_category(db, alice_id)

    response = await client.post(
        "/api/v1/operations",
        json={"category_id": str(category.id), "amount": "25.50", "kind": "expense"},
        headers=bearer(bob_token),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    bob_list = (await client.get("/api/v1/operations", headers=bearer(bob_token))).json()
    alice_list = (await client.get("/api/v1/operations", headers=bearer(alice_token))).json()
    assert bob_list["total"] == 0
    assert alice_list["total"] == 0


async def test_operations_list_only_own_sorted_desc(client, db) -> None:
    alice_id, alice_token = await register_and_login(client, "alice@test.io")
    bob_id, bob_token = await register_and_login(client, "bob@test.io")
    category = await seed_category(db, alice_id)
    await create_operation(
        client, alice_token, category.id, occurred_at="2026-10-05T10:00:00Z", amount="10.00"
    )
    await create_operation(
        client, alice_token, category.id, occurred_at="2026-10-01T10:00:00Z", amount="20.00"
    )
    bob_category = await seed_category(db, bob_id, name="У Боба")
    await create_operation(
        client, bob_token, bob_category.id, occurred_at="2026-10-03T10:00:00Z", amount="30.00"
    )

    body = (await client.get("/api/v1/operations", headers=bearer(alice_token))).json()
    assert body["total"] == 2
    assert [item["occurred_at"][:10] for item in body["items"]] == ["2026-10-05", "2026-10-01"]

    bob_list = (await client.get("/api/v1/operations", headers=bearer(bob_token))).json()
    assert bob_list["total"] == 1
    assert bob_list["items"][0]["user_id"] == str(bob_id)


async def test_operations_pagination_second_page_with_total(client, db) -> None:
    alice_id, alice_token = await register_and_login(client)
    category = await seed_category(db, alice_id)
    for day in range(1, 13):
        await create_operation(
            client,
            alice_token,
            category.id,
            occurred_at=f"2026-10-{day:02d}T12:00:00Z",
            amount=f"{day}.00",
        )

    body = (
        await client.get(
            "/api/v1/operations",
            params={"page": 2, "limit": 5},
            headers=bearer(alice_token),
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
            headers=bearer(alice_token),
        )
    ).json()
    assert [item["occurred_at"][:10] for item in tail["items"]] == ["2026-10-02", "2026-10-01"]


async def test_operations_filters_period_category_and_kind(client, db) -> None:
    alice_id, alice_token = await register_and_login(client)
    groceries = await seed_category(db, alice_id, name="Продукты")
    salary = await seed_category(db, alice_id, name="Зарплата")
    oct_expense = await create_operation(
        client, alice_token, groceries.id, occurred_at="2026-10-05T10:00:00Z", amount="10.00"
    )
    oct_income = await create_operation(
        client,
        alice_token,
        salary.id,
        occurred_at="2026-10-20T10:00:00Z",
        amount="50.00",
        kind="income",
    )
    await create_operation(
        client, alice_token, groceries.id, occurred_at="2026-09-15T10:00:00Z", amount="5.00"
    )

    period = (
        await client.get(
            "/api/v1/operations",
            params={"from": "2026-10-01", "to": "2026-10-31"},
            headers=bearer(alice_token),
        )
    ).json()
    assert period["total"] == 2
    assert {item["id"] for item in period["items"]} == {oct_expense["id"], oct_income["id"]}

    income_only = (
        await client.get(
            "/api/v1/operations",
            params={"from": "2026-10-01", "to": "2026-10-31", "type": "income"},
            headers=bearer(alice_token),
        )
    ).json()
    assert income_only["total"] == 1
    assert income_only["items"][0]["id"] == oct_income["id"]

    by_category = (
        await client.get(
            "/api/v1/operations",
            params={"from": "2026-10-01", "category_id": str(groceries.id)},
            headers=bearer(alice_token),
        )
    ).json()
    assert by_category["total"] == 1
    assert by_category["items"][0]["id"] == oct_expense["id"]

    empty_period = (
        await client.get(
            "/api/v1/operations",
            params={"from": "2026-11-01"},
            headers=bearer(alice_token),
        )
    ).json()
    assert empty_period["total"] == 0


async def test_operations_reject_broken_period_and_date_format(client, db) -> None:
    _, alice_token = await register_and_login(client)

    unordered = await client.get(
        "/api/v1/operations",
        params={"from": "2026-10-31", "to": "2026-10-01"},
        headers=bearer(alice_token),
    )
    assert unordered.status_code == 422

    unparsable = await client.get(
        "/api/v1/operations",
        params={"from": "не-дата"},
        headers=bearer(alice_token),
    )
    assert unparsable.status_code == 422


async def test_operations_patch_updates_amount_and_note(client, db) -> None:
    alice_id, alice_token = await register_and_login(client)
    category = await seed_category(db, alice_id)
    created = await create_operation(
        client, alice_token, category.id, occurred_at="2026-10-05T10:00:00Z"
    )

    body = (
        await client.patch(
            f"/api/v1/operations/{created['id']}",
            json={"amount": "30.00", "note": "обновлено"},
            headers=bearer(alice_token),
        )
    ).json()

    assert body["amount"] == "30.00"
    assert body["note"] == "обновлено"
    assert body["kind"] == "expense"

    async with db() as session:
        row = await session.get(Operation, UUID(created["id"]))
        assert row is not None
        assert row.amount_cents == 3000


async def test_operations_patch_rejects_null_for_not_null_fields(client, db) -> None:
    alice_id, alice_token = await register_and_login(client)
    category = await seed_category(db, alice_id)
    created = await create_operation(client, alice_token, category.id)

    response = await client.patch(
        f"/api/v1/operations/{created['id']}",
        json={"kind": None},
        headers=bearer(alice_token),
    )

    assert response.status_code == 422


async def test_operations_patch_foreign_returns_404_isolation(client, db) -> None:
    alice_id, alice_token = await register_and_login(client, "alice@test.io")
    _, bob_token = await register_and_login(client, "bob@test.io")
    category = await seed_category(db, alice_id)
    created = await create_operation(client, alice_token, category.id)

    response = await client.patch(
        f"/api/v1/operations/{created['id']}",
        json={"note": "взломано"},
        headers=bearer(bob_token),
    )
    assert response.status_code == 404

    untouched = (
        await client.get(f"/api/v1/operations/{created['id']}", headers=bearer(alice_token))
    ).json()
    assert untouched["note"] != "взломано"


async def test_operations_patch_foreign_category_isolation(client, db) -> None:
    alice_id, _ = await register_and_login(client, "alice@test.io")
    bob_id, bob_token = await register_and_login(client, "bob@test.io")
    foreign_category = await seed_category(db, alice_id)
    own_category = await seed_category(db, bob_id, name="У Боба")
    created = await create_operation(client, bob_token, own_category.id)

    response = await client.patch(
        f"/api/v1/operations/{created['id']}",
        json={"category_id": str(foreign_category.id)},
        headers=bearer(bob_token),
    )
    assert response.status_code == 404

    untouched = (
        await client.get(f"/api/v1/operations/{created['id']}", headers=bearer(bob_token))
    ).json()
    assert untouched["category_id"] == str(own_category.id)


async def test_operations_delete_own_removes(client, db) -> None:
    alice_id, alice_token = await register_and_login(client)
    category = await seed_category(db, alice_id)
    created = await create_operation(client, alice_token, category.id)

    deleted = (
        await client.delete(f"/api/v1/operations/{created['id']}", headers=bearer(alice_token))
    ).json()
    assert deleted["id"] == created["id"]

    assert (
        await client.get(f"/api/v1/operations/{created['id']}", headers=bearer(alice_token))
    ).status_code == 404
    listing = (await client.get("/api/v1/operations", headers=bearer(alice_token))).json()
    assert listing["total"] == 0


async def test_operations_delete_foreign_returns_404_isolation(client, db) -> None:
    alice_id, alice_token = await register_and_login(client, "alice@test.io")
    _, bob_token = await register_and_login(client, "bob@test.io")
    category = await seed_category(db, alice_id)
    created = await create_operation(client, alice_token, category.id)

    response = await client.delete(
        f"/api/v1/operations/{created['id']}", headers=bearer(bob_token)
    )
    assert response.status_code == 404

    kept = (
        await client.get(f"/api/v1/operations/{created['id']}", headers=bearer(alice_token))
    )
    assert kept.status_code == 200


async def test_operations_empty_list_returns_zero_total(client) -> None:
    _, alice_token = await register_and_login(client)

    body = (await client.get("/api/v1/operations", headers=bearer(alice_token))).json()
    assert body == {"items": [], "total": 0, "page": 1, "limit": 20}

    categories = (await client.get("/api/v1/categories", headers=bearer(alice_token))).json()
    assert categories == []


async def test_operations_require_authentication(client) -> None:
    assert (await client.get("/api/v1/operations")).status_code == 401
    assert (await client.post("/api/v1/operations", json={})).status_code == 401
    assert (await client.get("/api/v1/categories")).status_code == 401
