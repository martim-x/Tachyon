"""Сборка обработчиков доменных событий."""

from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock
from app.core.events import BudgetThresholdReached, EventBus
from app.domains.budget.thresholds import BudgetThresholdService
from app.domains.notification.service import NotificationService


def build_event_bus(
    session: AsyncSession,
) -> EventBus:
    """Собрать шину событий для одной транзакции."""
    event_bus = EventBus()
    notification_service = NotificationService(session)

    async def handle_budget_threshold(
        event: BudgetThresholdReached,
    ) -> None:
        await notification_service.handle_budget_threshold(
            event,
        )

    event_bus.subscribe(
        BudgetThresholdReached,
        handle_budget_threshold,
    )

    return event_bus


async def evaluate_budget_notifications(
    *,
    session: AsyncSession,
    user_id: UUID,
    month: date,
    clock: Clock,
) -> None:
    """Проверить лимиты и обработать опубликованные события."""
    event_bus = build_event_bus(session)

    await BudgetThresholdService(
        session,
        event_bus,
        clock,
    ).evaluate(
        user_id=user_id,
        month=month,
    )
