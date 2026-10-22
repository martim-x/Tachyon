
from datetime import date
from http import HTTPStatus

import pytest

pytestmark = pytest.mark.asyncio

URL = "/api/v1/budget_limits"
MONTH = date(2026, 10, 1).isoformat()


async def test_empty_list(api_client_a):
    response = await api_client_a.client.get(URL)

    assert response.status_code == HTTPStatus.OK, response.text
    assert response.json() == []


async def test_create_and_conflict(api_client_a, category_factory):
    category = await category_factory(api_client_a.user)
    payload = {
        "category_id": str(category.id),
        "month": MONTH,
        "limit_amount_cents": 1000,
    }

    created = await api_client_a.client.post(URL, json=payload)

    assert created.status_code == HTTPStatus.CREATED, created.text
    assert created.json()["user_id"] == str(api_client_a.user.id)
    assert created.json()["limit_amount_cents"] == 1000

    listed = await api_client_a.client.get(URL)

    assert listed.status_code == HTTPStatus.OK, listed.text
    assert len(listed.json()) == 1
    assert listed.json()[0]["category_id"] == str(category.id)

    duplicate = await api_client_a.client.post(URL, json=payload)
    assert duplicate.status_code == HTTPStatus.CONFLICT, duplicate.text


async def test_zero_limit_error(api_client_a, category_factory):
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


async def test_update_limit(api_client_a, category_factory):
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


async def test_status_ok(api_client_a, category_factory):
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


