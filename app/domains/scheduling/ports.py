"""Порт для создания операций из scheduling (docs/02 §Ports).

Планировщик не импортирует ledger напрямую — зависит от этого протокола.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from app.core.money import Money


class OperationWriter(Protocol):
    """Интерфейс для создания операции повторяющимся правилом."""

    async def __call__(
        self,
        *,
        category_id: UUID,
        amount: Money,
        kind: str,
        occurred_at: datetime,
        note: str | None = None,
    ) -> None: ...


OperationWriterFn = Callable[
    [UUID, Money, str, datetime, str | None],
    None,
]


async def create_operation_impl(
    session,
    *,
    category_id: UUID,
    amount: Money,
    kind: str,
    occurred_at: datetime,
    note: str | None = None,
) -> None:
    """Реализация по умолчанию через ledger repository (для тестов/дефолта)."""
    from app.domains.ledger.repository import OperationRepository

    repo = OperationRepository(session)
    fields: dict = {
        "category_id": category_id,
        "kind": kind,
        "note": note,
    }
    if occurred_at is not None:
        fields["occurred_at"] = occurred_at.astimezone(UTC)
    await repo.create(amount=amount, **fields)