"""Сервис повторяющихся операций: расчёт дат, clamp, catch-up (docs/03 §S4.1-4.3).

Не использует date.today() — время через Clock (NFR-1).
Зависит от порта OperationWriter, не от ledger напрямую.
"""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

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
        user_id: UUID | str | None = None,
        until: datetime | None = None,
        dry_run: bool = False,
        date_from: datetime | None = None,
    ) -> list[RecurringExecution]:
        """Создать операции за все наступившие периоды.

        UNIQUE(rule_id, period_date) является последним рубежом
        идемпотентности при параллельных запусках.
        """

        def as_utc(value: datetime) -> datetime:
            if value.tzinfo is None:
                return value.replace(tzinfo=UTC)
            return value.astimezone(UTC)

        if until is None:
            from app.core.clock import SystemClock

            until = SystemClock().now()

        until = as_utc(until)
        date_from = as_utc(date_from) if date_from is not None else None

        statement = select(RecurringRule).where(RecurringRule.is_active.is_(True))

        # Ручной запуск обрабатывает правила текущего пользователя.
        # Фоновый планировщик передаёт user_id=None и обрабатывает всех.
        if user_id is not None:
            statement = statement.where(RecurringRule.user_id == user_id)

        result = await self._session.execute(statement)
        rules = list(result.scalars().all())

        generated: list[RecurringExecution] = []

        for rule in rules:
            # next_run_at — единственный указатель следующего периода.
            # last_run_at нельзя использовать как старт: иначе период
            # может быть обработан повторно.
            current = as_utc(rule.next_run_at)
            original_day = rule.start_date.day
            last_processed: datetime | None = None

            while current <= until:
                if rule.end_date is not None and current.date() > rule.end_date:
                    break

                # Параметр from ограничивает ручной диапазон запуска.
                if date_from is not None and current < date_from:
                    last_processed = current
                    current = next_run(
                        rule.kind,
                        current,
                        interval=rule.interval,
                        original_day=original_day,
                    )
                    continue

                execution = RecurringExecution(
                    id=uuid4(),
                    rule_id=rule.id,
                    user_id=rule.user_id,
                    period_date=current.date(),
                    operation_id=None,
                )

                if dry_run:
                    # dry-run ничего не записывает и не меняет правило.
                    existing_statement = select(RecurringExecution.id).where(
                        RecurringExecution.rule_id == rule.id,
                        RecurringExecution.period_date == current.date(),
                    )
                    existing_id = await self._session.scalar(existing_statement)

                    if existing_id is None:
                        generated.append(execution)

                else:
                    inserted = False

                    try:
                        # SAVEPOINT откатывает только конфликтующую вставку.
                        # Предыдущие созданные операции не теряются.
                        async with self._session.begin_nested():
                            self._session.add(execution)
                            await self._session.flush()
                            inserted = True
                    except IntegrityError:
                        # Другой запуск уже обработал этот период.
                        inserted = False

                    if inserted:
                        operation_id = await self.operation_writer(
                            user_id=rule.user_id,
                            category_id=rule.category_id,
                            amount=Money.from_cents(rule.amount_cents),
                            kind="expense",
                            occurred_at=current,
                            recurring_execution_id=execution.id,
                            note=rule.note,
                            source="recurring",
                        )

                        execution.operation_id = operation_id
                        await self._session.flush()
                        generated.append(execution)

                last_processed = current
                current = next_run(
                    rule.kind,
                    current,
                    interval=rule.interval,
                    original_day=original_day,
                )

            if not dry_run and last_processed is not None:
                rule.last_run_at = last_processed
                rule.next_run_at = current

        if not dry_run:
            await self._session.flush()

        return generated
