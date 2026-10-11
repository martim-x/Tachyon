"""Часы проекта (docs/02 §«Ядро»): Clock + SystemClock + FrozenClock.

Домены получают время только через Clock, а не через datetime.now напрямую,
поэтому в тестах время подменяется фикстурой frozen_clock без monkeypatch
и без ожидания таймеров (docs/06 §Структура тестов).
"""

from datetime import UTC, date, datetime
from typing import Protocol


class Clock(Protocol):
    """Протокол часов: текущая дата и текущий момент в UTC."""

    def today(self) -> date: ...

    def now(self) -> datetime: ...


class SystemClock:
    """Системное время: единственная точка чтения реальных часов в доменах."""

    def today(self) -> date:
        return datetime.now(UTC).date()

    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    """Фиксированное время тестов: день задаётся и не меняется.

    now() возвращает полдень UTC этого дня: граница суток не перескакивает,
    поэтому тесты не зависят от момента запуска.
    """

    def __init__(self, day: date | str) -> None:
        self._day = date.fromisoformat(day) if isinstance(day, str) else day

    def today(self) -> date:
        return self._day

    def now(self) -> datetime:
        return datetime(self._day.year, self._day.month, self._day.day, 12, tzinfo=UTC)
