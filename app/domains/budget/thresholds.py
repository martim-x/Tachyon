"""Публикация событий о достижении порогов бюджетных лимитов."""

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock
from app.core.events import (
    BudgetThreshold,
    BudgetThresholdReached,
    EventPublisher,
    ThresholdCategory,
)
from app.domains.budget.models import BudgetLimit
from app.domains.budget.service import reached_threshold
from app.domains.ledger.models import Category, Operation


def first_day_of_next_month(month: date) -> date:
    """Получить первый день следующего месяца."""
    if month.month == 12:
        return date(month.year + 1, 1, 1)

    return date(month.year, month.month + 1, 1)


def day_start(day: date) -> datetime:
    """Получить начало календарного дня в UTC."""
    return datetime(
        day.year,
        day.month,
        day.day,
        tzinfo=UTC,
    )


class BudgetThresholdService:
    """Проверяет лимиты и публикует агрегированные события."""

    def __init__(
        self,
        session: AsyncSession,
        publisher: EventPublisher,
        clock: Clock,
    ) -> None:
        self._session = session
        self._publisher = publisher
        self._clock = clock

    async def evaluate(
        self,
        *,
        user_id: UUID,
        month: date,
    ) -> tuple[BudgetThresholdReached, ...]:
        """Проверить фактические расходы пользователя за месяц."""
        normalized_month = date(
            month.year,
            month.month,
            1,
        )
        next_month = first_day_of_next_month(normalized_month)
        now = self._clock.now()

        statement = (
            select(
                BudgetLimit.category_id,
                Category.name.label("category_name"),
                BudgetLimit.limit_amount_cents,
                func.coalesce(
                    func.sum(Operation.amount_cents),
                    0,
                ).label("spent_amount_cents"),
            )
            .select_from(BudgetLimit)
            .join(
                Category,
                and_(
                    Category.id == BudgetLimit.category_id,
                    Category.user_id == BudgetLimit.user_id,
                ),
            )
            .outerjoin(
                Operation,
                and_(
                    Operation.user_id == BudgetLimit.user_id,
                    Operation.category_id == BudgetLimit.category_id,
                    Operation.kind == "expense",
                    Operation.occurred_at >= day_start(normalized_month),
                    Operation.occurred_at < day_start(next_month),
                    Operation.occurred_at <= now,
                ),
            )
            .where(
                BudgetLimit.user_id == user_id,
                BudgetLimit.month == normalized_month,
            )
            .group_by(
                BudgetLimit.category_id,
                Category.name,
                BudgetLimit.limit_amount_cents,
            )
            .order_by(Category.name)
        )

        rows = (await self._session.execute(statement)).mappings().all()

        grouped: dict[
            BudgetThreshold,
            list[ThresholdCategory],
        ] = {
            "WARNING": [],
            "EXCEEDED": [],
        }

        for row in rows:
            limit_amount_cents = int(
                row["limit_amount_cents"],
            )
            spent_amount_cents = int(
                row["spent_amount_cents"],
            )
            reached = reached_threshold(
                limit_amount_cents,
                spent_amount_cents,
            )

            if reached is None:
                continue

            grouped[reached].append(
                ThresholdCategory(
                    category_id=row["category_id"],
                    category_name=str(row["category_name"]),
                    spent_amount_cents=spent_amount_cents,
                    limit_amount_cents=limit_amount_cents,
                )
            )

        events: list[BudgetThresholdReached] = []

        threshold_order: tuple[BudgetThreshold, ...] = (
            "WARNING",
            "EXCEEDED",
        )

        for event_threshold in threshold_order:
            categories = grouped[event_threshold]

            if not categories:
                continue

            event = BudgetThresholdReached(
                user_id=user_id,
                month=normalized_month,
                threshold=event_threshold,
                categories=tuple(categories),
                occurred_at=now,
            )
            await self._publisher.publish(event)
            events.append(event)

        return tuple(events)
