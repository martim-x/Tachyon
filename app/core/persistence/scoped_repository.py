"""Базовый класс всех доменных репозиториев (docs/02 «Изоляция данных», механизм 3).

Фильтр WHERE user_id = ... накладывается здесь и не может быть забыт в конкретном
хендлере: конструктор не принимает user_id снаружи, идентификатор берётся из
UserContext, session приватный, query-builder наружу не выдаётся. Пустой контекст
это исключение, а не пустая выдача. Внешние ключи проверяются на владение
(docs/03 §S3.2): ссылка обязана вести на строку того же пользователя, иначе
NotFound - 404, а не 403.
"""

from collections.abc import Mapping, Sequence
from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import Select, Table, exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.errors import NotFound
from app.core.persistence import Base
from app.core.user_context import get_current_user

T = TypeVar("T", bound=Base)


class ScopedRepository(Generic[T]):
    """Любой доступ к данным идёт только через этот класс.

    Паттерн Repository с Template Method-хуками: наследник объявляет только
    model, все методы ходят через _scoped(), поэтому фильтр нельзя забыть.
    """

    model: type[T]

    def __init__(self, session: AsyncSession) -> None:
        if not hasattr(self.model, "user_id"):
            raise TypeError(
                f"{self.model.__name__} без user_id не может быть обёрнут в ScopedRepository"
            )
        self._session = session

    @property
    def _user_id(self) -> UUID:
        return get_current_user()  # PermissionDenied без контекста

    def _scoped(self) -> Select[tuple[T]]:
        return select(self.model).where(self.model.user_id == self._user_id)  # type: ignore[attr-defined]

    async def list(
        self,
        *,
        order_by: Sequence[InstrumentedAttribute[Any]] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> Sequence[T]:
        """Все записи текущего пользователя; чужие физически не попадают в выборку."""
        stmt = self._scoped()
        if order_by is not None:
            stmt = stmt.order_by(*order_by)
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_by_id(self, pk: UUID) -> T | None:
        """WHERE id = :id AND user_id = :current; чужая запись неотличима от отсутствующей."""
        stmt = self._scoped().where(self.model.id == pk)  # type: ignore[attr-defined]
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_404(self, pk: UUID) -> T:
        """Запись текущего пользователя; иначе NotFound - 404, а не 403."""
        obj = await self.get_by_id(pk)
        if obj is None:
            raise NotFound(f"{self.model.__name__} не найден")
        return obj

    def _fk_ownership_targets(self) -> dict[str, Table]:
        """FK-поля модели, которые обязаны вести на строку текущего пользователя.

        Цель без колонки user_id (users, справочные таблицы) не проверяется:
        владение там подтверждает JWT, а не репозиторий. Цель ищется по
        декларации FK в metadata, поэтому домену не нужен импорт чужой модели.
        """
        targets: dict[str, Table] = {}
        for name, column in self.model.__table__.columns.items():
            for fk in column.foreign_keys:
                target = fk.column.table
                if "user_id" in target.c:
                    targets[name] = target
        return targets

    async def _assert_fk_ownership(self, values: Mapping[str, Any]) -> None:
        """Ссылка по FK ведёт только на запись того же владельца (docs/03 §S3.2).

        Чужая или несуществующая цель это NotFound: 404, а не 403, чтобы ответ
        не подтверждал существование чужих строк.
        """
        user_id = self._user_id
        for field, target in self._fk_ownership_targets().items():
            value = values.get(field)
            if value is None:
                continue
            stmt = select(exists().where(target.c.id == value, target.c.user_id == user_id))
            result = await self._session.execute(stmt)
            if not result.scalar_one():
                raise NotFound(f"{field}: связанная запись не найдена")

    async def create(self, **fields: Any) -> T:
        """user_id всегда приходит из UserContext, а не из аргументов вызывающего."""
        await self._assert_fk_ownership(fields)
        obj = self.model(user_id=self._user_id, **fields)
        self._session.add(obj)
        await self._session.flush()
        return obj

    async def update(self, pk: UUID, **fields: Any) -> T:
        """Чужая запись не найдётся, поэтому не изменится; подменять id и user_id нельзя."""
        if fields.keys() & {"id", "user_id"}:
            raise TypeError("id и user_id нельзя менять через update")
        obj = await self.get_or_404(pk)
        await self._assert_fk_ownership(fields)
        for name, value in fields.items():
            setattr(obj, name, value)
        await self._session.flush()
        return obj

    async def delete(self, pk: UUID) -> T:
        """Чужая запись не найдётся: 404, и строка остаётся в БД."""
        obj = await self.get_or_404(pk)
        await self._session.delete(obj)
        await self._session.flush()
        return obj