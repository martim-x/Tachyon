"""Доступ к операциям и категориям (docs/02: репозиторий - единственная граница денег).

Сумма приходит и уходит как Money: запись amount_cents = int(money * 100),
чтение Money.from_cents(amount_cents). Ни api, ни service колонку не трогают.
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import exists, func, select

from app.core.money import Money
from app.core.persistence.scoped_repository import ScopedRepository
from app.domains.ledger.models import Category, Operation


def _day_start(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


class OperationRepository(ScopedRepository[Operation]):
    model = Operation

    async def create(self, *, amount: Money | None = None, **fields: Any) -> Operation:
        """Запись денег идёт в копейках (docs/02, правило 5); без Money строку отвергнет БД."""
        if amount is not None:
            fields["amount_cents"] = amount.to_cents()
        return await super().create(**fields)

    async def update(
        self,
        pk: UUID,
        *,
        amount: Money | None = None,
        **fields: Any,
    ) -> Operation:
        if amount is not None:
            fields["amount_cents"] = amount.to_cents()
        return await super().update(pk, **fields)

    @staticmethod
    def to_money(operation: Operation) -> Money:
        """Чтение денег: граница конвертации одна - репозиторий (docs/02)."""
        return Money.from_cents(operation.amount_cents)

    async def page(
        self,
        *,
        page: int,
        limit: int,
        date_from: date | None = None,
        date_to: date | None = None,
        category_id: UUID | None = None,
        kind: str | None = None,
    ) -> tuple[Sequence[Operation], int]:
        """Страница своих операций по дате убыванию; total - по тем же фильтрам."""
        stmt = self._scoped()
        if date_from is not None:
            stmt = stmt.where(Operation.occurred_at >= _day_start(date_from))
        if date_to is not None:
            upper_bound = _day_start(date_to + timedelta(days=1))
            stmt = stmt.where(Operation.occurred_at < upper_bound)
        if category_id is not None:
            stmt = stmt.where(Operation.category_id == category_id)
        if kind is not None:
            stmt = stmt.where(Operation.kind == kind)

        counted = await self._session.execute(select(func.count()).select_from(stmt.subquery()))
        total = counted.scalar_one()

        ordered = stmt.order_by(Operation.occurred_at.desc(), Operation.id.desc())
        listed = await self._session.execute(ordered.offset((page - 1) * limit).limit(limit))
        return listed.scalars().all(), total

    async def exists_for_category(self, category_id: UUID) -> bool:
        """Есть ли операция текущего пользователя в этой категории.

        Фильтр user_id берётся из _scoped: чужие операции не видны и не
        блокируют удаление чужой категории (её и так не отдаст get_or_404).
        """
        scoped = self._scoped().where(Operation.category_id == category_id)
        found = await self._session.execute(select(exists(scoped)))
        return bool(found.scalar_one())


class CategoryRepository(ScopedRepository[Category]):
    model = Category
