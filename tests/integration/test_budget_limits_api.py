import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from http import HTTPStatus

import pytest

pytestmark = pytest.mark.asyncio

URL = "/api/v1/budget-limits"
MONTH = date(2026, 10, 1).isoformat()


async def test_empty_list(api_client_a):
    response = await api_client_a.client.get(URL)

    assert response.status_code == HTTPStatus.OK, response.text
    assert response.json() == []


async def test_create_and_conflict(
    api_client_a,
    category_factory,
):
    category = await category_factory(api_client_a.user)
    payload = {
        "category_id": str(category.id),
        "month": MONTH,
        "limit_amount_cents": 1000,
    }

    created = await api_client_a.client.post(
        URL,
        json=payload,
    )

    assert created.status_code == HTTPStatus.CREATED, created.text
    assert created.json()["user_id"] == str(api_client_a.user.id)
    assert created.json()["limit_amount_cents"] == 1000

    listed = await api_client_a.client.get(URL)

    assert listed.status_code == HTTPStatus.OK, listed.text
    assert len(listed.json()) == 1
    assert listed.json()[0]["category_id"] == str(category.id)

    duplicate = await api_client_a.client.post(
        URL,
        json=payload,
    )

    assert duplicate.status_code == HTTPStatus.CONFLICT
    assert duplicate.text


async def test_zero_limit_error(
    api_client_a,
    category_factory,
):
    category = await category_factory(api_client_a.user)

    response = await api_client_a.client.post(
        URL,
        json={
            "category_id": str(category.id),
            "month": MONTH,
            "limit_amount_cents": 0,
        },
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, response.text


async def test_update_limit(
    api_client_a,
    category_factory,
):
    category = await category_factory(api_client_a.user)

    created = await api_client_a.client.post(
        URL,
        json={
            "category_id": str(category.id),
            "month": MONTH,
            "limit_amount_cents": 500,
        },
    )
    assert created.status_code == HTTPStatus.CREATED, created.text

    updated = await api_client_a.client.put(
        f"{URL}/{category.id}",
        params={
            "month": MONTH,
            "limit_amount_cents": 700,
        },
    )

    assert updated.status_code == HTTPStatus.OK, updated.text
    assert updated.json()["limit_amount_cents"] == 700

    listed = await api_client_a.client.get(URL)

    assert listed.status_code == HTTPStatus.OK, listed.text
    assert len(listed.json()) == 1
    assert listed.json()[0]["limit_amount_cents"] == 700


async def test_update_limit_rejects_zero_amount(
    api_client_a,
    category_factory,
):
    category = await category_factory(
        api_client_a.user,
    )

    created = await api_client_a.client.post(
        URL,
        json={
            "category_id": str(category.id),
            "month": MONTH,
            "limit_amount_cents": 500,
        },
    )

    assert created.status_code == HTTPStatus.CREATED, created.text

    response = await api_client_a.client.put(
        f"{URL}/{category.id}",
        params={
            "month": MONTH,
            "limit_amount_cents": 0,
        },
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_status_ok(
    api_client_a,
    category_factory,
):
    category = await category_factory(api_client_a.user)

    created = await api_client_a.client.post(
        URL,
        json={
            "category_id": str(category.id),
            "month": MONTH,
            "limit_amount_cents": 500,
        },
    )
    assert created.status_code == HTTPStatus.CREATED, created.text

    response = await api_client_a.client.get(f"{URL}/status")

    assert response.status_code == HTTPStatus.OK, response.text

    data = response.json()
    assert len(data) == 1
    assert data[0]["category_id"] == str(category.id)
    assert data[0]["month"] == MONTH
    assert data[0]["status"] == "OK"
    assert data[0]["spent_amount_cents"] == 0
    assert isinstance(
        data[0]["percent"],
        int | float,
    )
    assert not isinstance(
        data[0]["percent"],
        str,
    )


async def test_month_is_normalized_to_first_day(
    api_client_a,
    category_factory,
):
    category = await category_factory(api_client_a.user)

    created = await api_client_a.client.post(
        URL,
        json={
            "category_id": str(category.id),
            "month": "2026-10-15",
            "limit_amount_cents": 1000,
        },
    )

    assert created.status_code == HTTPStatus.CREATED, created.text
    assert created.json()["month"] == "2026-10-01"

    duplicate = await api_client_a.client.post(
        URL,
        json={
            "category_id": str(category.id),
            "month": "2026-10-25",
            "limit_amount_cents": 2000,
        },
    )

    assert duplicate.status_code == HTTPStatus.CONFLICT
    assert duplicate.text

    updated = await api_client_a.client.put(
        f"{URL}/{category.id}",
        params={
            "month": "2026-10-31",
            "limit_amount_cents": 1500,
        },
    )

    assert updated.status_code == HTTPStatus.OK, updated.text
    assert updated.json()["month"] == "2026-10-01"
    assert updated.json()["limit_amount_cents"] == 1500


async def test_concurrent_creation_does_not_return_500(
    api_client_a,
    category_factory,
):
    category = await category_factory(api_client_a.user)
    payload = {
        "category_id": str(category.id),
        "month": MONTH,
        "limit_amount_cents": 1000,
    }

    first, second = await asyncio.gather(
        api_client_a.client.post(URL, json=payload),
        api_client_a.client.post(URL, json=payload),
    )

    assert sorted([first.status_code, second.status_code]) == [
        HTTPStatus.CREATED,
        HTTPStatus.CONFLICT,
    ]


async def test_status_uses_real_spending_and_forecast(
    api_client_a,
    category_factory,
    operation_factory,
):
    # Фиксируем текущую дату, чтобы результат прогноза
    # не зависел от дня запуска теста.

    category = await category_factory(
        api_client_a.user,
        name="Продукты",
        kind="expense",
    )

    created = await api_client_a.client.post(
        URL,
        json={
            "category_id": str(category.id),
            "month": "2026-10-15",
            "limit_amount_cents": 100_000,
        },
    )
    assert created.status_code == HTTPStatus.CREATED, created.text

    # Операция до отчётной даты входит в факт.
    await operation_factory(
        api_client_a.user,
        Decimal("700.00"),
        category=category,
        kind="expense",
        occurred_at=datetime(
            2026,
            10,
            10,
            12,
            tzinfo=UTC,
        ),
    )

    # Будущая операция не входит в факт и текущий темп.
    await operation_factory(
        api_client_a.user,
        Decimal("500.00"),
        category=category,
        kind="expense",
        occurred_at=datetime(
            2026,
            10,
            20,
            12,
            tzinfo=UTC,
        ),
    )

    response = await api_client_a.client.get(f"{URL}/status")

    assert response.status_code == HTTPStatus.OK, response.text

    data = response.json()
    assert len(data) == 1

    status_data = data[0]

    assert status_data["month"] == "2026-10-01"
    assert status_data["limit_amount_cents"] == 100_000
    assert status_data["spent_amount_cents"] == 70_000
    assert status_data["remaining_amount_cents"] == 30_000

    # 700 / 15 прошедших дней * 31 день = 1446.67.
    assert status_data["projected_amount_cents"] == 144_667
    assert status_data["status"] == "EXCEEDED_PROJECTED"


async def test_past_month_projection_equals_final_spending(
    api_client_a,
    category_factory,
    operation_factory,
):
    category = await category_factory(
        api_client_a.user,
        name="Сентябрьские расходы",
        kind="expense",
    )

    created = await api_client_a.client.post(
        URL,
        json={
            "category_id": str(category.id),
            "month": "2026-09-15",
            "limit_amount_cents": 1000,
        },
    )
    assert created.status_code == HTTPStatus.CREATED, created.text

    await operation_factory(
        api_client_a.user,
        Decimal("7.00"),
        category=category,
        kind="expense",
        occurred_at=datetime(
            2026,
            9,
            10,
            12,
            tzinfo=UTC,
        ),
    )

    response = await api_client_a.client.get(f"{URL}/status")

    assert response.status_code == HTTPStatus.OK, response.text

    status_data = response.json()[0]

    assert status_data["month"] == "2026-09-01"
    assert status_data["spent_amount_cents"] == 700
    assert status_data["projected_amount_cents"] == 700
    assert status_data["remaining_amount_cents"] == 300
    assert status_data["status"] == "OK"


async def test_future_month_has_zero_spending_and_projection(
    api_client_a,
    category_factory,
    operation_factory,
):
    category = await category_factory(
        api_client_a.user,
        name="Ноябрьские расходы",
        kind="expense",
    )

    created = await api_client_a.client.post(
        URL,
        json={
            "category_id": str(category.id),
            "month": "2026-11-20",
            "limit_amount_cents": 1000,
        },
    )
    assert created.status_code == HTTPStatus.CREATED, created.text

    # Операция существует в БД, но относительно FrozenClock
    # ноябрь ещё не наступил.
    await operation_factory(
        api_client_a.user,
        Decimal("9.00"),
        category=category,
        kind="expense",
        occurred_at=datetime(
            2026,
            11,
            5,
            12,
            tzinfo=UTC,
        ),
    )

    response = await api_client_a.client.get(f"{URL}/status")

    assert response.status_code == HTTPStatus.OK, response.text

    status_data = response.json()[0]

    assert status_data["month"] == "2026-11-01"
    assert status_data["spent_amount_cents"] == 0
    assert status_data["projected_amount_cents"] == 0
    assert status_data["remaining_amount_cents"] == 1000
    assert status_data["status"] == "OK"
