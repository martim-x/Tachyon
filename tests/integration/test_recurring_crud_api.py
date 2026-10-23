"""CRUD повторяющихся правил и изоляция пользователей."""

from uuid import uuid4

import pytest

from tests.conftest import (
    CategoryFactory,
    LoggedInClient,
    RuleFactory,
)

pytestmark = pytest.mark.integration

URL = "/api/v1/recurring/rules"


async def test_recurring_rule_crud_uses_uuid_and_is_scoped(
    api_client_a: LoggedInClient,
    api_client_b: LoggedInClient,
    rule_factory: RuleFactory,
) -> None:
    own_rule = await rule_factory(
        api_client_a.user,
    )
    foreign_rule = await rule_factory(
        api_client_b.user,
    )

    listed = await api_client_a.client.get(URL)

    assert listed.status_code == 200
    assert {item["id"] for item in listed.json()} == {
        str(own_rule.id),
    }

    fetched = await api_client_a.client.get(
        f"{URL}/{own_rule.id}",
    )

    assert fetched.status_code == 200
    assert fetched.json()["id"] == str(own_rule.id)

    patched = await api_client_a.client.patch(
        f"{URL}/{own_rule.id}",
        json={
            "note": "Обновлённое правило",
        },
    )

    assert patched.status_code == 200
    assert patched.json()["note"] == ("Обновлённое правило")

    foreign = await api_client_a.client.get(
        f"{URL}/{foreign_rule.id}",
    )
    missing = await api_client_a.client.get(
        f"{URL}/{uuid4()}",
    )

    assert foreign.status_code == 404
    assert missing.status_code == 404
    assert foreign.json() == missing.json()
    assert foreign.json()["error"]["code"] == ("NOT_FOUND")

    deleted = await api_client_a.client.delete(
        f"{URL}/{own_rule.id}",
    )

    assert deleted.status_code == 204
    assert deleted.content == b""


async def test_recurring_rule_rejects_foreign_category(
    api_client_a: LoggedInClient,
    api_client_b: LoggedInClient,
    category_factory: CategoryFactory,
) -> None:
    own_category = await category_factory(
        api_client_a.user,
    )
    foreign_category = await category_factory(
        api_client_b.user,
    )

    base_payload = {
        "kind": "monthly",
        "interval": 1,
        "amount_cents": 100000,
        "note": "Аренда",
        "start_date": "2026-10-01",
        "end_date": None,
    }

    foreign_response = await api_client_a.client.post(
        URL,
        json={
            **base_payload,
            "category_id": str(foreign_category.id),
        },
    )
    missing_response = await api_client_a.client.post(
        URL,
        json={
            **base_payload,
            "category_id": str(uuid4()),
        },
    )

    assert foreign_response.status_code == 404
    assert missing_response.status_code == 404
    assert foreign_response.json() == (missing_response.json())

    created = await api_client_a.client.post(
        URL,
        json={
            **base_payload,
            "category_id": str(own_category.id),
        },
    )

    assert created.status_code == 201
    rule_id = created.json()["id"]

    patched = await api_client_a.client.patch(
        f"{URL}/{rule_id}",
        json={
            "category_id": str(foreign_category.id),
        },
    )

    assert patched.status_code == 404

    unchanged = await api_client_a.client.get(
        f"{URL}/{rule_id}",
    )

    assert unchanged.status_code == 200
    assert unchanged.json()["category_id"] == str(own_category.id)
