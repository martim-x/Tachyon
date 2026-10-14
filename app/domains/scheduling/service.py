"""Сервис повторяющихся операций: расчёт дат, clamp, catch-up (docs/03 §S4.1-4.3).

Не использует date.today() — время через Clock (NFR-1).
Зависит от порта OperationWriter, не от ledger напрямую.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.core.money import Money
from app.domains.scheduling.models import RecurringExecution, RecurringRule
from app.domains.scheduling.ports import OperationWriter


def _last_day_of_month(year: int, month: int) -> int:
    """Возвращает номер последнего дня месяца (28/29/30/31)."""
    if month == 12:
        return (date(year + 1, 1, 1) - timedelta(days=1)).day
    return (date(year, month + 1, 1) - timedelta(days=1)).day


def _next_month(year: int, month: int) -> tuple[int, int]:
    if month == 12:
        return year + 1, 1
    return year, month + 1


def next_run(
    rule_kind: str,
    after: datetime,
    *,
    interval: int = 1,
    original_day: int | None = None,
) -> datetime:
    """Следующая дата запуска после `after` (включительно).

    kind: daily/weekly/monthly.
    daily: +interval дней.
    weekly: +interval недель (тот же день недели).
    monthly: +interval месяцев, день сохраняется; если дня нет в целевом
    месяце (31 в феврале) — последний день месяца.

    after должен иметь таймзону (UTC). Результат — полдень UTC целевого дня.
    """
    if after.tzinfo is None:
        raise ValueError("after must be timezone-aware")

    base = after.replace(hour=12, minute=0, second=0, microsecond=0, tzinfo=UTC)

    if rule_kind == "daily":
        return base + timedelta(days=interval)

    if rule_kind == "weekly":
        return base + timedelta(weeks=interval)

    if rule_kind == "monthly":
        year = base.year
        month = base.month
        # Используем original_day если передан, иначе day из after
        day = original_day if original_day is not None else base.day

        # Сдвигаем на interval месяцев без clamp на промежуточных месяцах
        for _ in range(interval):
            year, month = _next_month(year, month)

        # Clamp только для итогового месяца
        last_day = _last_day_of_month(year, month)
        day = min(day, last_day)

        return datetime(year, month, day, 12, 0, 0, tzinfo=UTC)

    raise ValueError(f"unknown kind: {rule_kind}")


class RecurringService:
    """Бизнес-логика правил повтора: CRUD + генерация + идемпотентность."""

    def __init__(
        self,
        session: AsyncSession,
        operation_writer: OperationWriter | None = None,
    ) -> None:
        self._session = session
        self._operation_writer = operation_writer

    @property
    def operation_writer(self) -> OperationWriter:
        if self._operation_writer is None:
            from app.domains.scheduling.ports import create_operation_impl

            self._operation_writer = lambda **kw: create_operation_impl(self._session, **kw)
        return self._operation_writer

    async def create_rule(self, rule: RecurringRule) -> RecurringRule:
        self._session.add(rule)
        await self._session.flush()
        return rule

    async def get_rule(self, rule_id: str, user_id: str) -> RecurringRule:
        rule = await self._session.get(RecurringRule, rule_id)
        if rule is None or rule.user_id != user_id:
            raise NotFound("Правило не найдено")
        return rule

    async def list_rules(self, user_id: str) -> list[RecurringRule]:
        result = await self._session.execute(
            select(RecurringRule).where(RecurringRule.user_id == user_id)
        )
        return list(result.scalars().all())

    async def update_rule(
        self,
        rule_id: str,
        user_id: str,
        **fields,
    ) -> RecurringRule:
        rule = await self.get_rule(rule_id, user_id)
        for k, v in fields.items():
            if v is not None:
                setattr(rule, k, v)
            elif k in ("note", "end_date"):  # Разрешаем явно очистить эти поля
                setattr(rule, k, v)
        await self._session.flush()
        return rule

    async def delete_rule(self, rule_id: str, user_id: str) -> bool:
        rule = await self.get_rule(rule_id, user_id)
        rule.is_active = False  # мягкое удаление
        await self._session.flush()
        return True

    async def generate_due_operations(
        self,
        user_id: str,
        until: datetime | None = None,
        dry_run: bool = False,
    ) -> list[RecurringExecution]:
        """
        Создаёт операции за все пропущенные периоды до `until` (или now()).

        Использует RecurringExecution с UNIQUE(rule_id, period_date) для идемпотентности:
        повторный вызов не создаёт дубликаты.

        dry_run=True — только preview, не пишет в БД и не меняет состояние правил.
        """
        if self._operation_writer is None:
            from app.domains.scheduling.ports import create_operation_impl

            self._operation_writer = lambda **kw: create_operation_impl(self._session, **kw)

        if until is None:
            from app.core.clock import SystemClock

            until = SystemClock().now()

        rules = await self.list_rules(user_id)
        created: list[RecurringExecution] = []

        for rule in rules:
            if not rule.is_active:
                continue

            # Определяем старт: max(start_date, last_run_at)
            if rule.last_run_at is not None:
                current = rule.last_run_at
            else:
                # Первый запуск — start_date в полдень UTC
                current = datetime(
                    rule.start_date.year,
                    rule.start_date.month,
                    rule.start_date.day,
                    12,
                    0,
                    0,
                    tzinfo=UTC,
                )

            # Сохраняем исходный день для monthly (чтобы не дрейфовать)
            original_day = rule.start_date.day

            while current <= until:
                # Проверка end_date для текущего периода
                if rule.end_date is not None:
                    end_dt = datetime(
                        rule.end_date.year,
                        rule.end_date.month,
                        rule.end_date.day,
                        23,
                        59,
                        59,
                        tzinfo=UTC,
                    )
                    if current > end_dt:
                        break

                period_date = current.date()

                # Идемпотентность: пытаемся создать execution
                execution = RecurringExecution(
                    rule_id=rule.id,
                    user_id=rule.user_id,
                    period_date=period_date,
                )
                self._session.add(execution)
                try:
                    await self._session.flush()
                except IntegrityError:
                    # Уже существует — пропускаем этот период
                    await self._session.rollback()
                    current = next_run(
                        rule.kind, current, interval=rule.interval, original_day=original_day
                    )
                    continue

                if not dry_run:
                    # Создаём операцию через порт
                    await self._operation_writer(
                        user_id=rule.user_id,
                        category_id=rule.category_id,
                        amount=Money.from_cents(rule.amount_cents),
                        kind="expense",
                        occurred_at=current,
                        note=rule.note,
                        source="recurring",
                    )
                    created.append(execution)
                else:
                    # dry_run: создаём execution объект для ответа, но не пишем в БД
                    # Откатываем flush для этого execution
                    await self._session.rollback()
                    created.append(execution)

                # Сдвигаем на следующий период
                current = next_run(
                    rule.kind, current, interval=rule.interval, original_day=original_day
                )

            # Обновляем next_run_at правила (только если не dry_run)
            if not dry_run:
                rule.next_run_at = current
                rule.last_run_at = current - timedelta(seconds=1)
                await self._session.flush()

        return created