from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import FrozenClock
from app.domains.ledger.models import Operation
from app.domains.scheduling.models import RecurringExecution, RecurringRule
from app.domains.scheduling.service import RecurringService
from tests.conftest import RuleFactory, UserFactory

pytestmark = pytest.mark.integration


async def test_two_runs_do_not_create_duplicate_operations(
    db_session: async_sessionmaker[AsyncSession],
    user_factory: UserFactory,
    rule_factory: RuleFactory,
    frozen_clock: FrozenClock,
) -> None:
    user, _token = await user_factory("scheduler@test.io")
    rule = await rule_factory(
        user,
        kind="daily",
        start_date=date(2026, 10, 1),
    )

    async with db_session() as session:
        service = RecurringService(session)

        first_run = await service.generate_due_operations(
            user_id=user.id,
            until=frozen_clock.now(),
        )
        await session.commit()

    assert len(first_run) == 15
    assert all(item.operation_id is not None for item in first_run)

    async with db_session() as session:
        service = RecurringService(session)

        second_run = await service.generate_due_operations(
            user_id=user.id,
            until=frozen_clock.now(),
        )
        await session.commit()

    assert second_run == []

    async with db_session() as session:
        execution_count = await session.scalar(select(func.count()).select_from(RecurringExecution))
        operation_count = await session.scalar(select(func.count()).select_from(Operation))
        stored_rule = await session.get(RecurringRule, rule.id)

    assert execution_count == 15
    assert operation_count == 15
    assert stored_rule is not None
    assert stored_rule.last_run_at is not None
    assert stored_rule.last_run_at.date() == date(2026, 10, 15)
    assert stored_rule.next_run_at.date() == date(2026, 10, 16)


async def test_dry_run_does_not_write_or_advance_rule(
    db_session: async_sessionmaker[AsyncSession],
    user_factory: UserFactory,
    rule_factory: RuleFactory,
    frozen_clock: FrozenClock,
) -> None:
    user, _token = await user_factory("dry-run@test.io")
    rule = await rule_factory(
        user,
        kind="daily",
        start_date=date(2026, 10, 1),
    )

    original_next_run_at = rule.next_run_at

    async with db_session() as session:
        service = RecurringService(session)

        preview = await service.generate_due_operations(
            user_id=user.id,
            until=frozen_clock.now(),
            dry_run=True,
        )
        await session.commit()

    assert len(preview) == 15
    assert all(item.operation_id is None for item in preview)

    async with db_session() as session:
        execution_count = await session.scalar(select(func.count()).select_from(RecurringExecution))
        operation_count = await session.scalar(select(func.count()).select_from(Operation))
        stored_rule = await session.get(RecurringRule, rule.id)

    assert execution_count == 0
    assert operation_count == 0
    assert stored_rule is not None
    assert stored_rule.last_run_at is None
    stored_next_run_at = stored_rule.next_run_at

    if stored_next_run_at.tzinfo is None:
        stored_next_run_at = stored_next_run_at.replace(tzinfo=original_next_run_at.tzinfo)

    assert stored_next_run_at == original_next_run_at


async def test_existing_execution_is_skipped_without_breaking_transaction(
    db_session: async_sessionmaker[AsyncSession],
    user_factory: UserFactory,
    rule_factory: RuleFactory,
) -> None:
    user, _token = await user_factory("duplicate@test.io")
    rule = await rule_factory(
        user,
        kind="daily",
        start_date=date(2026, 10, 1),
    )

    # Имитируем второй воркер или перезапуск после частично
    # завершённого запуска: execution уже существует,
    # но next_run_at правила ещё указывает на ту же дату.
    async with db_session() as session:
        session.add(
            RecurringExecution(
                user_id=user.id,
                rule_id=rule.id,
                period_date=date(2026, 10, 1),
                operation_id=None,
            )
        )
        await session.commit()

    async with db_session() as session:
        service = RecurringService(session)

        generated = await service.generate_due_operations(
            user_id=user.id,
            until=datetime(2026, 10, 3, 12, 0, tzinfo=UTC),
        )
        await session.commit()

    assert [item.period_date for item in generated] == [
        date(2026, 10, 2),
        date(2026, 10, 3),
    ]

    async with db_session() as session:
        execution_count = await session.scalar(select(func.count()).select_from(RecurringExecution))
        operation_count = await session.scalar(select(func.count()).select_from(Operation))
        stored_rule = await session.get(RecurringRule, rule.id)

    assert execution_count == 3
    assert operation_count == 2
    assert stored_rule is not None
    assert stored_rule.next_run_at.date() == date(2026, 10, 4)
