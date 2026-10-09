"""Бизнес-слой операций: изоляция даёт ScopedRepository, деньги - Money."""

from collections.abc import Sequence
from datetime import UTC
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.money import Money
from app.domains.ledger.models import Category, Operation
from app.domains.ledger.repository import CategoryRepository, OperationRepository
from app.domains.ledger.schemas import (
    OperationCreate,
    OperationListQuery,
    OperationUpdate,
)


class OperationService:
    """Сценарии операций: user_id приходит из UserContext, а не из аргументов."""

    def __init__(self, session: AsyncSession) -> None:
        self._operations = OperationRepository(session)

    async def create(self, payload: OperationCreate) -> Operation:
        fields: dict[str, Any] = {
            "category_id": payload.category_id,
            "kind": payload.kind,
            "note": payload.note,
        }
        if payload.occurred_at is not None:
            fields["occurred_at"] = payload.occurred_at.astimezone(UTC)
        return await self._operations.create(amount=Money(payload.amount), **fields)

    async def list_page(self, query: OperationListQuery) -> tuple[Sequence[Operation], int]:
        return await self._operations.page(
            page=query.page,
            limit=query.limit,
            date_from=query.date_from,
            date_to=query.date_to,
            category_id=query.category_id,
            kind=query.kind,
        )

    async def get(self, operation_id: UUID) -> Operation:
        return await self._operations.get_or_404(operation_id)

    async def update(self, operation_id: UUID, payload: OperationUpdate) -> Operation:
        fields = payload.model_dump(exclude_unset=True)
        amount = fields.pop("amount", None)
        if fields.get("occurred_at") is not None:
            fields["occurred_at"] = fields["occurred_at"].astimezone(UTC)
        return await self._operations.update(
            operation_id,
            amount=Money(amount) if amount is not None else None,
            **fields,
        )

    async def delete(self, operation_id: UUID) -> Operation:
        return await self._operations.delete(operation_id)


class CategoryService:
    def __init__(self, session: AsyncSession) -> None:
        self._categories = CategoryRepository(session)

    async def list(self) -> Sequence[Category]:
        return await self._categories.list()
