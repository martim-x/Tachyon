"""Сервис повторяющихся операций: расчёт дат, clamp, catch-up (docs/03 §S4.1-4.3).

Не использует date.today() — время через Clock (NFR-1).
Зависит от порта OperationWriter, не от ledger напрямую.
"""

from datetime import UTC, date, datetime, timedelta

from app.core.clock import Clock
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
        day = base.day

        for _ in range(interval):
            year, month = _next_month(year, month)
            last_day = _last_day_of_month(year, month)
            day = min(day, last_day)

        return datetime(year, month, day, 12, 0, 0, tzinfo=UTC)

    raise ValueError(f"unknown kind: {rule_kind}")


def compute_next_run(
    rule_kind: str,
    start_date: date,
    end_date: date | None,
    after: datetime,
    *,
    interval: int = 1,
    clock: Clock | None = None,
) -> datetime | None:
    """
    Полный расчёт следующего запуска с учётом границ правила.

    Возвращает None, если правило уже завершилось (после end_date или
    следующего запуска нет до start_date).
    """
    if clock is None:
        from app.core.clock import SystemClock

        clock = SystemClock()

    now = clock.now()

    # Правило ещё не началось
    if now < datetime(start_date.year, start_date.month, start_date.day, tzinfo=UTC):
        return datetime(start_date.year, start_date.month, start_date.day, 12, 0, 0, tzinfo=UTC)

    # Правило уже закончилось
    if end_date is not None:
        end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=UTC)
        if now > end_dt:
            return None

    # Следующий запуск строго после `after` (который может быть now или last_run_at)
    candidate = next_run(rule_kind, after, interval=interval)

    # Проверка end_date для кандидата
    if end_date is not None:
        end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=UTC)
        if candidate > end_dt:
            return None

    return candidate


class RecurringService:
    """Бизнес-логика правил повтора: CRUD + генерация + идемпотентность."""

    def __init__(
        self,
        session,
        operation_writer: OperationWriter | None = None,
    ) -> None:
        self._session = session
        self._operation_writer = operation_writer

    async def create_rule(self, rule: RecurringRule) -> RecurringRule:
        self._session.add(rule)
        await self._session.flush()
        return rule

    async def get_rule(self, rule_id: str) -> RecurringRule | None:
        return await self._session.get(RecurringRule, rule_id)

    async def list_rules(self) -> list[RecurringRule]:
        from sqlalchemy import select
        result = await self._session.execute(select(RecurringRule))
        return list(result.scalars().all())

    async def update_rule(self, rule_id: str, **fields) -> RecurringRule | None:
        rule = await self.get_rule(rule_id)
        if rule is None:
            return None
        for k, v in fields.items():
            if v is not None:
                setattr(rule, k, v)
        await self._session.flush()
        return rule

    async def delete_rule(self, rule_id: str) -> bool:
        rule = await self.get_rule(rule_id)
        if rule is None:
            return False
        rule.is_active = False  # мягкое удаление
        await self._session.flush()
        return True

    async def generate_due_operations(
        self,
        until: datetime | None = None,
        dry_run: bool = False,
    ) -> list[RecurringExecution]:
        """
        Создаёт операции за все пропущенные периоды до `until` (или now()).

        Использует RecurringExecution с UNIQUE(rule_id, period_date) для идемпотентности:
        повторный вызов не создаёт дубликаты.
        """
        if self._operation_writer is None:
            # Ленивая загрузка дефолтной реализации
            from app.domains.scheduling.ports import create_operation_impl

            self._operation_writer = lambda **kw: create_operation_impl(self._session, **kw)

        if until is None:
            from app.core.clock import SystemClock

            until = SystemClock().now()

        rules = await self.list_rules()
        created = []

        for rule in rules:
            if not rule.is_active:
                continue
            if rule.end_date and rule.end_date < until.date():
                continue

            current = rule.next_run_at
            while current <= until:
                # Идемпотентность: проверяем/создаём execution
                execution = RecurringExecution(
                    rule_id=rule.id,
                    period_date=current.date(),
                )
                self._session.add(execution)
                try:
                    await self._session.flush()
                except Exception:
                    await self._session.rollback()
                    # Уже существует — пропускаем этот период
                    pass
                else:
                    # Создаём операцию через порт
                    if not dry_run:
                        await self._operation_writer(
                            category_id=rule.category_id,
                            amount=Money(rule.amount_cents / 100),
                            kind="expense",
                            occurred_at=current,
                            note=rule.note,
                        )
                    created.append(execution)

                # Сдвигаем на следующий период
                current = next_run(rule.kind, current, interval=rule.interval)

            # Обновляем next_run_at правила
            rule.next_run_at = current
            rule.last_run_at = current - timedelta(seconds=1)
            await self._session.flush()

        if not dry_run:
            await self._session.commit()

        return created