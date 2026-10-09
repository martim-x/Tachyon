"""Чистое ядро прогноза (docs/03 §S6.2, docs/06 §Формулы).

Без ORM, HTTP-фреймворка и табличных библиотек: вход - Decimal и даты,
отчётная дата всегда параметром (текущее время ядро не читает). Округление
до копеек выполняется один раз, в самом конце расчёта, через money() с
ROUND_HALF_UP.
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.domains.forecasting import calendar_math
from app.domains.forecasting.strategies import WHOLE_MONTH, PaceStrategy

MONEY_QUANTUM = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    """Сумма в копейках: ROUND_HALF_UP, а не банковское округление и не round()."""
    return Decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def linear_forecast(
    spent_to_date: Decimal,
    days_elapsed: int,
    days_in_month: int,
    *,
    pace: PaceStrategy = WHOLE_MONTH,
    recent_window_total: Decimal = Decimal("0.00"),
    extra_known_amounts: Decimal = Decimal("0.00"),
) -> Decimal:
    """Базовая формула (S6.2 T1): projected = spent + rate * days_remaining + extra.

    Деление на ноль невозможно: темп при days_elapsed = 0 равен нулю (FR-1).
    Округление один раз в конце: промежуточный темп остаётся дробным Decimal.
    """
    daily_rate = pace.daily_rate(
        spent_to_date=spent_to_date,
        days_elapsed=days_elapsed,
        recent_window_total=recent_window_total,
    )
    days_remaining = days_in_month - days_elapsed
    projected = spent_to_date + daily_rate * days_remaining + extra_known_amounts
    return money(projected)


def forecast_month(
    spent_to_date: Decimal,
    year: int,
    month: int,
    as_of: date,
    *,
    pace: PaceStrategy = WHOLE_MONTH,
    recent_window_total: Decimal = Decimal("0.00"),
    extra_known_amounts: Decimal = Decimal("0.00"),
) -> dict:
    """Результат прогноза: календарь, темп, итог и пометка достоверности.

    low_confidence при days_elapsed < 3: прогноз статистически мусорный,
    но посчитать его надо - помечаем, а не прячем (docs/06).
    """
    dim = calendar_math.days_in_month(year, month)
    elapsed = calendar_math.days_elapsed(year, month, as_of)
    days_remaining = dim - elapsed
    daily_rate = pace.daily_rate(
        spent_to_date=spent_to_date,
        days_elapsed=elapsed,
        recent_window_total=recent_window_total,
    )
    projected_total = money(
        spent_to_date + daily_rate * days_remaining + extra_known_amounts
    )
    return {
        "year": year,
        "month": month,
        "pace": pace.name,
        "days_in_month": dim,
        "days_elapsed": elapsed,
        "days_remaining": days_remaining,
        "spent_to_date": money(spent_to_date),
        "daily_rate": money(daily_rate),
        "projected_total": projected_total,
        "low_confidence": elapsed < 3,
    }
