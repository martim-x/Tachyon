"""Порт создания операций из scheduling.

Scheduling зависит от интерфейса OperationWriter и не импортирует ledger
в бизнес-логике. Конкретная реализация подключается на уровне приложения.
"""

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, SystemClock
from app.core.money import Money
from app.core.user_context import user_scope
from app.infrastructure.event_handlers import evaluate_budget_notifications


class OperationWriter(Protocol):
    """Создаёт операцию для выполнения повторяющегося правила."""

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
        """Вернуть UUID созданной операции."""
        ...


async def create_operation_impl(
    session: AsyncSession,
    *,
    user_id: UUID,
    category_id: UUID,
    amount: Money,
    kind: str,
    occurred_at: datetime,
    recurring_execution_id: UUID,
    note: str | None = None,
    source: str = "recurring",
    clock: Clock | None = None,
) -> UUID:
    """Реализация порта через репозиторий домена ledger."""

    # Локальный импорт сохраняет направление зависимости:
    # scheduling знает только порт, а не реализацию ledger.
    from app.domains.ledger.repository import OperationRepository

    repository = OperationRepository(session)

    with user_scope(user_id):
        operation = await repository.create(
            category_id=category_id,
            amount=amount,
            kind=kind,
            occurred_at=occurred_at.astimezone(UTC),
            recurring_execution_id=recurring_execution_id,
            note=note,
            source=source,
        )

    await evaluate_budget_notifications(
        session=session,
        user_id=user_id,
        month=operation.occurred_at.date(),
        clock=clock or SystemClock(),
    )

    return operation.id
