"""E2E-тест: пустой пользователь регистрируется и делает первый цикл действий.

Docs: docs/03 §S9.4, docs/06 AC12.
Покрывает путь: регистрация → создание категории → операция → чтение списка → удаление.
"""

import pytest

from tests.conftest import ApiClientFactory

pytestmark = pytest.mark.e2e


async def test_empty_user_full_flow_register_category_operation(
    api_client: ApiClientFactory,
) -> None:
    """Полный цикл нового пользователя: регистрация → категория → операция → чтение → удаление."""
    # 1. Регистрация нового пользователя
    client = api_client()
    reg_response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@test.io",
            "password": "Secret123!",
            "password_confirm": "Secret123!",
        },
    )
    assert reg_response.status_code == 201, reg_response.text
    reg_body = reg_response.json()
    assert "id" in reg_body
    assert reg_body["email"] == "newuser@test.io"

    # Login to get access token
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "newuser@test.io", "password": "Secret123!"},
    )
    assert login_response.status_code == 200, login_response.text
    login_body = login_response.json()
    assert "access_token" in login_body
    assert login_body["token_type"] == "bearer"
    access_token = login_body["access_token"]

    # Авторизованный клиент
    authed = api_client(token=access_token)

    # 2. Список категорий пуст
    cats = (await authed.get("/api/v1/categories")).json()
    assert cats == []

    # 3. Создание категории
    cat_response = await authed.post(
        "/api/v1/categories",
        json={"name": "Продукты", "kind": "expense"},
    )
    assert cat_response.status_code == 201, cat_response.text
    category = cat_response.json()
    cat_id = category["id"]
    assert category["name"] == "Продукты"
    assert category["kind"] == "expense"
    assert category["user_id"] == reg_body["id"]

    # 4. Список категорий содержит созданную
    cats = (await authed.get("/api/v1/categories")).json()
    assert len(cats) == 1
    assert cats[0]["id"] == cat_id

    # 5. Список операций пуст
    ops = (await authed.get("/api/v1/operations")).json()
    assert ops == {"items": [], "total": 0, "page": 1, "limit": 20}

    # 6. Создание операции
    op_response = await authed.post(
        "/api/v1/operations",
        json={
            "category_id": cat_id,
            "amount": "150.75",
            "kind": "expense",
            "note": "Покупка продуктов",
            "occurred_at": "2026-10-15T14:30:00Z",
        },
    )
    assert op_response.status_code == 201, op_response.text
    operation = op_response.json()
    op_id = operation["id"]
    assert operation["amount"] == "150.75"
    assert operation["kind"] == "expense"
    assert operation["note"] == "Покупка продуктов"
    assert operation["category_id"] == cat_id
    assert operation["source"] == "manual"

    # 7. Чтение операции
    get_op = await authed.get(f"/api/v1/operations/{op_id}")
    assert get_op.status_code == 200
    assert get_op.json()["id"] == op_id

    # 8. Список операций содержит созданную
    ops = (await authed.get("/api/v1/operations")).json()
    assert ops["total"] == 1
    assert ops["items"][0]["id"] == op_id
    assert ops["items"][0]["amount"] == "150.75"

    # 9. Фильтр по категории
    filtered = (await authed.get("/api/v1/operations", params={"category_id": cat_id})).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["id"] == op_id

    # 10. Обновление операции (PATCH)
    patch_response = await authed.patch(
        f"/api/v1/operations/{op_id}",
        json={"amount": "155.00", "note": "Покупка продуктов (обновлено)"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["amount"] == "155.00"
    assert patch_response.json()["note"] == "Покупка продуктов (обновлено)"

    # 11. Удаление операции
    del_response = await authed.delete(f"/api/v1/operations/{op_id}")
    assert del_response.status_code == 204
    assert (await authed.get(f"/api/v1/operations/{op_id}")).status_code == 404
    ops = (await authed.get("/api/v1/operations")).json()
    assert ops["total"] == 0

    # Категории не удаляются в этом тесте (нет DELETE эндпоинта для категорий)


async def test_empty_user_two_users_isolated(
    api_client: ApiClientFactory,
) -> None:
    """Два пользователя не видят данные друг друга."""
    # Пользователь 1
    client1 = api_client()
    reg1 = await client1.post(
        "/api/v1/auth/register",
        json={
            "email": "user1@test.io",
            "password": "Secret123!",
            "password_confirm": "Secret123!",
        },
    )
    assert reg1.status_code == 201

    # Login to get token
    login1 = await client1.post(
        "/api/v1/auth/login",
        json={"email": "user1@test.io", "password": "Secret123!"},
    )
    assert login1.status_code == 200
    token1 = login1.json()["access_token"]
    c1 = api_client(token=token1)

    cat1 = (await c1.post("/api/v1/categories", json={"name": "Cat1", "kind": "expense"})).json()
    op1 = (
        await c1.post(
            "/api/v1/operations",
            json={"category_id": cat1["id"], "amount": "100.00", "kind": "expense"},
        )
    ).json()

    # Пользователь 2
    client2 = api_client()
    reg2 = await client2.post(
        "/api/v1/auth/register",
        json={
            "email": "user2@test.io",
            "password": "Secret123!",
            "password_confirm": "Secret123!",
        },
    )
    assert reg2.status_code == 201

    # Login to get token
    login2 = await client2.post(
        "/api/v1/auth/login",
        json={"email": "user2@test.io", "password": "Secret123!"},
    )
    assert login2.status_code == 200
    token2 = login2.json()["access_token"]
    c2 = api_client(token=token2)

    cat2 = (await c2.post("/api/v1/categories", json={"name": "Cat2", "kind": "expense"})).json()
    op2 = (
        await c2.post(
            "/api/v1/operations",
            json={"category_id": cat2["id"], "amount": "200.00", "kind": "expense"},
        )
    ).json()

    # Изоляция: user1 видит только свои
    c1_cats = (await c1.get("/api/v1/categories")).json()
    c1_ops = (await c1.get("/api/v1/operations")).json()
    assert len(c1_cats) == 1
    assert c1_cats[0]["id"] == cat1["id"]
    assert c1_ops["total"] == 1
    assert c1_ops["items"][0]["id"] == op1["id"]

    # User2 видит только свои
    c2_cats = (await c2.get("/api/v1/categories")).json()
    c2_ops = (await c2.get("/api/v1/operations")).json()
    assert len(c2_cats) == 1
    assert c2_cats[0]["id"] == cat2["id"]
    assert c2_ops["total"] == 1
    assert c2_ops["items"][0]["id"] == op2["id"]

    # Попытка доступа к чужим данным: и операция, и категория по id — 404.
    assert (await c1.get(f"/api/v1/operations/{op2['id']}")).status_code == 404
    assert (await c2.get(f"/api/v1/operations/{op1['id']}")).status_code == 404
    assert (await c1.get(f"/api/v1/categories/{cat2['id']}")).status_code == 404
    assert (await c2.get(f"/api/v1/categories/{cat1['id']}")).status_code == 404


async def test_empty_user_invalid_login_then_valid(
    api_client: ApiClientFactory,
) -> None:
    """Сначала неверный пароль, потом верный — получаем токен."""
    client = api_client()
    # Регистрация
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "loginuser@test.io",
            "password": "Secret123!",
            "password_confirm": "Secret123!",
        },
    )

    # Неверный пароль
    bad_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "loginuser@test.io", "password": "WrongPassword"},
    )
    assert bad_login.status_code == 401

    # Верный пароль
    good_login = await client.post(
        "/api/v1/auth/login",
        json={"email": "loginuser@test.io", "password": "Secret123!"},
    )
    assert good_login.status_code == 200
    assert "access_token" in good_login.json()


async def test_empty_user_pagination_and_sorting(
    api_client: ApiClientFactory,
) -> None:
    """Проверка пагинации и сортировки на данных одного пользователя."""
    client = api_client()
    reg = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "pageuser@test.io",
            "password": "Secret123!",
            "password_confirm": "Secret123!",
        },
    )
    assert reg.status_code == 201

    # Login to get token
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "pageuser@test.io", "password": "Secret123!"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    authed = api_client(token=token)

    cat = (await authed.post("/api/v1/categories", json={"name": "Test", "kind": "expense"})).json()

    # Создаём 12 операций в разные даты
    for day in range(1, 13):
        await authed.post(
            "/api/v1/operations",
            json={
                "category_id": cat["id"],
                "amount": f"{day * 10}.00",
                "kind": "expense",
                "occurred_at": f"2026-10-{day:02d}T12:00:00Z",
            },
        )

    # Первая страница (limit=5)
    page1 = (await authed.get("/api/v1/operations", params={"page": 1, "limit": 5})).json()
    assert page1["page"] == 1
    assert page1["limit"] == 5
    assert page1["total"] == 12
    # Сортировка desc по occurred_at: последние 5 = 12, 11, 10, 9, 8
    assert [item["occurred_at"][:10] for item in page1["items"]] == [
        "2026-10-12",
        "2026-10-11",
        "2026-10-10",
        "2026-10-09",
        "2026-10-08",
    ]

    # Вторая страница
    page2 = (await authed.get("/api/v1/operations", params={"page": 2, "limit": 5})).json()
    assert page2["page"] == 2
    assert page2["total"] == 12
    assert [item["occurred_at"][:10] for item in page2["items"]] == [
        "2026-10-07",
        "2026-10-06",
        "2026-10-05",
        "2026-10-04",
        "2026-10-03",
    ]

    # Третья страница (хвост)
    page3 = (await authed.get("/api/v1/operations", params={"page": 3, "limit": 5})).json()
    assert page3["page"] == 3
    assert [item["occurred_at"][:10] for item in page3["items"]] == [
        "2026-10-02",
        "2026-10-01",
    ]
