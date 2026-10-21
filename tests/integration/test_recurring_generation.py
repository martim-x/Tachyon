from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import FrozenClock
from app.core.money import Money
from app.domains.ledger.models import Operation
from app.domains.scheduling.models import RecurringExecution, RecurringRule
from app.domains.scheduling.ports import create_operation_impl
from app.domains.scheduling.service import RecurringService
from tests.conftest import RuleFactory, UserFactory

pytestmark = pytest.mark.integration


class SelectivelyFailingWriter:
    """Имитирует ошибку только для одной категории."""

    def __init__(
        self,
        session: AsyncSession,
        bad_category_id: UUID,
    ) -> None:
        self._session = session
        self._bad_category_id = bad_category_id

    async def __call__(
        self,
        *,
        user_id: UUID,
        category_id: UUID,
        amount: Money,
        kind: str,
        occurred_at: datetime,
        recurring_execution_id: UUID,
        note: str | None = None,
        source: str = "recurring",
    ) -> UUID:
        if category_id == self._bad_category_id:
            raise RuntimeError("Имитируем ошибку одного правила")

        return await create_operation_impl(
            self._session,
            user_id=user_id,
            category_id=category_id,
            amount=amount,
            kind=kind,
            occurred_at=occurred_at,
            recurring_execution_id=recurring_execution_id,
            note=note,
            source=source,
        )


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


async def test_broken_rule_does_not_block_other_users(
    db_session: async_sessionmaker[AsyncSession],
    user_factory: UserFactory,
    rule_factory: RuleFactory,
) -> None:
    bad_user, _bad_token = await user_factory("broken-rule@test.io")
    good_user, _good_token = await user_factory("working-rule@test.io")

    bad_rule = await rule_factory(
        bad_user,
        kind="daily",
        start_date=date(2026, 10, 1),
    )
    good_rule = await rule_factory(
        good_user,
        kind="daily",
        start_date=date(2026, 10, 1),
    )

    async with db_session() as session:
        writer = SelectivelyFailingWriter(
            session,
            bad_category_id=bad_rule.category_id,
        )
        service = RecurringService(
            session,
            operation_writer=writer,
        )

        generated = await service.generate_due_operations(
            user_id=None,
            until=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
            continue_on_error=True,
        )
        await session.commit()

    assert len(generated) == 1
    assert generated[0].rule_id == good_rule.id

    async with db_session() as session:
        bad_execution_count = await session.scalar(
            select(func.count())
            .select_from(RecurringExecution)
            .where(RecurringExecution.rule_id == bad_rule.id)
        )
        good_execution_count = await session.scalar(
            select(func.count())
            .select_from(RecurringExecution)
            .where(RecurringExecution.rule_id == good_rule.id)
        )
        operation_count = await session.scalar(select(func.count()).select_from(Operation))
        stored_bad_rule = await session.get(
            RecurringRule,
            bad_rule.id,
        )
        stored_good_rule = await session.get(
            RecurringRule,
            good_rule.id,
        )

    assert bad_execution_count == 0
    assert good_execution_count == 1
    assert operation_count == 1

    assert stored_bad_rule is not None
    assert stored_good_rule is not None
    assert stored_bad_rule.next_run_at.date() == date(2026, 10, 1)
    assert stored_good_rule.next_run_at.date() == date(2026, 10, 2)


async def test_real_run_does_not_drop_periods_before_date_from(
    db_session: async_sessionmaker[AsyncSession],
    user_factory: UserFactory,
    rule_factory: RuleFactory,
) -> None:
    user, _token = await user_factory("catch-up@test.io")
    await rule_factory(
        user,
        kind="daily",
        start_date=date(2026, 10, 1),
    )

    async with db_session() as session:
        service = RecurringService(session)

        generated = await service.generate_due_operations(
            user_id=user.id,
            date_from=datetime(2026, 10, 3, tzinfo=UTC),
            until=datetime(2026, 10, 3, 12, 0, tzinfo=UTC),
            dry_run=False,
        )
        await session.commit()

    assert [item.period_date for item in generated] == [
        date(2026, 10, 1),
        date(2026, 10, 2),
        date(2026, 10, 3),
    ]
