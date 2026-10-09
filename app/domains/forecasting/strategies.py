"""Режимы темпа трат (docs/02 §«Два режима темпа», docs/06 §Формулы).

Оба режима - стратегии с общим протоколом daily_rate: ни одна не делит на
нуль, при days_elapsed = 0 темп равен 0, а не ZeroDivisionError (S6.2).
"""

from decimal import Decimal
from typing import Protocol

RECENT_WINDOW_DAYS = 7


class PaceStrategy(Protocol):
    """Протокол темпа: имя режима и ставка за день на одних и тех же входах."""

    name: str

    def daily_rate(
        self,
        *,
        spent_to_date: Decimal,
        days_elapsed: int,
        recent_window_total: Decimal,
    ) -> Decimal: ...


class WholeMonthPace:
    """Темп по всему месяцу с 1-го числа: spent_to_date / days_elapsed."""

    name = "WHOLE_MONTH"

    def daily_rate(
        self,
        *,
        spent_to_date: Decimal,
        days_elapsed: int,
        recent_window_total: Decimal,
    ) -> Decimal:
        if days_elapsed == 0:
            return Decimal("0.00")
        return spent_to_date / days_elapsed


class RecentWindowPace:
    """Темп по свежим тратам: recent_window_total за последние 7 дней.

    Окно ограничено days_elapsed, чтобы в первый день не растягивать
    однодневную сумму на семь (docs/06, пояснение к pace == "RECENT_WINDOW").
    """

    name = "RECENT_WINDOW"

    def daily_rate(
        self,
        *,
        spent_to_date: Decimal,
        days_elapsed: int,
        recent_window_total: Decimal,
    ) -> Decimal:
        window_days = min(RECENT_WINDOW_DAYS, max(days_elapsed, 1))
        if window_days == 0:
            return Decimal("0.00")
        return recent_window_total / window_days


WHOLE_MONTH = WholeMonthPace()
RECENT_WINDOW = RecentWindowPace()
