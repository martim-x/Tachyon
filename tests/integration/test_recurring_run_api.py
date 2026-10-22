from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domains.ledger.models import Operation
from app.domains.scheduling.models import RecurringExecution
from tests.conftest import LoggedInClient, RuleFactory

pytestmark = pytest.mark.integration


async def test_manual_run_is_dry_and_idempotent(
    api_client_a: LoggedInClient,
    rule_factory: RuleFactory,
    db_session: async_sessionmaker[AsyncSession],
) -> None:
    await rule_factory(
        api_client_a.user,
        kind="daily",
        start_date=date(2026, 10, 1),
    )

    payload = {
        "from": "2026-10-01",
        "to": "2026-10-03",
        "dry_run": True,
    }

    preview_response = await api_client_a.client.post(
        "/api/v1/recurring/rules/run",
        json=payload,
    )

    assert preview_response.status_code == 200
    assert len(preview_response.json()) == 3
    assert all(item["operation_id"] is None for item in preview_response.json())

    async with db_session() as session:
        preview_execution_count = await session.scalar(
            select(func.count()).select_from(RecurringExecution)
        )
        preview_operation_count = await session.scalar(select(func.count()).select_from(Operation))

    assert preview_execution_count == 0
    assert preview_operation_count == 0

    payload["dry_run"] = False

    first_response = await api_client_a.client.post(
        "/api/v1/recurring/rules/run",
        json=payload,
    )
    second_response = await api_client_a.client.post(
        "/api/v1/recurring/rules/run",
        json=payload,
    )

    assert first_response.status_code == 200
    assert len(first_response.json()) == 3
    assert all(item["operation_id"] is not None for item in first_response.json())

    assert second_response.status_code == 200
    assert second_response.json() == []

    async with db_session() as session:
        execution_count = await session.scalar(select(func.count()).select_from(RecurringExecution))
        operation_count = await session.scalar(select(func.count()).select_from(Operation))

    assert execution_count == 3
    assert operation_count == 3


async def test_manual_run_rejects_reversed_period(
    api_client_a: LoggedInClient,
) -> None:
    response = await api_client_a.client.post(
        "/api/v1/recurring/rules/run",
        json={
            "from": "2026-10-10",
            "to": "2026-10-01",
            "dry_run": False,
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
