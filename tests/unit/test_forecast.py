"""Кейсы AC1-AC12 спеки прогноза (docs/06 «Прогноз: таблица краевых случаев»).

Ожидаемые числа взяты из таблицы спеки, а не из реализации (docs/03 §S9.1:
тесты пишутся под спецификацию, каждый кейс ссылается на свой AC в docstring).
"""

from datetime import date
from decimal import Decimal

import pytest

from app.domains.forecasting import calendar_math
from app.domains.forecasting.service import forecast_month, linear_forecast, money
from app.domains.forecasting.strategies import RECENT_WINDOW, WHOLE_MONTH


def test_ac1_zero_spent_projects_zero() -> None:
    """AC1 Нулевые траты: октябрь 31 день, as_of 15-е, spent 0.00 -> projected 0.00."""
    result = forecast_month(Decimal("0.00"), 2026, 10, date(2026, 10, 15))
    assert result["days_elapsed"] == 15
    assert result["days_remaining"] == 16
    assert result["daily_rate"] == Decimal("0.00")
    assert result["projected_total"] == Decimal("0.00")


def test_ac2_first_day_of_month_marks_low_confidence() -> None:
    """AC2 Первый день месяца: 10.00 за один день -> 310.00, low_confidence=true."""
    result = forecast_month(Decimal("10.00"), 2026, 10, date(2026, 10, 1))
    assert result["days_elapsed"] == 1
    assert result["days_remaining"] == 30
    assert result["daily_rate"] == Decimal("10.00")
    assert result["projected_total"] == Decimal("310.00")
    assert result["low_confidence"] is True


def test_ac3_first_day_without_data() -> None:
    """AC3 Первый день, данных нет: rate 0.00 и projected 0.00 без исключений."""
    result = forecast_month(Decimal("0.00"), 2026, 10, date(2026, 10, 1))
    assert result["daily_rate"] == Decimal("0.00")
    assert result["projected_total"] == Decimal("0.00")


def test_ac4_completed_month_equals_spent() -> None:
    """AC4 Последний день месяца: days_remaining=0, projected = spent 1240.50."""
    result = forecast_month(Decimal("1240.50"), 2026, 10, date(2026, 10, 31))
    assert result["days_remaining"] == 0
    assert result["projected_total"] == Decimal("1240.50")


@pytest.mark.parametrize(
    ("year", "month", "as_of_day", "spent", "expected_rate", "expected_projected"),
    [
        pytest.param(
            2027, 2, 14, Decimal("700.00"), Decimal("50.00"), Decimal("1400.00"),
            id="ac5-february-28",
        ),
        pytest.param(
            2028, 2, 10, Decimal("500.00"), Decimal("50.00"), Decimal("1450.00"),
            id="ac6-february-29-leap",
        ),
        pytest.param(
            2026, 4, 15, Decimal("300.00"), Decimal("20.00"), Decimal("600.00"),
            id="ac7-april-30",
        ),
        pytest.param(
            2026, 1, 20, Decimal("1000.00"), Decimal("50.00"), Decimal("1550.00"),
            id="ac8-january-31",
        ),
    ],
)
def test_ac5_ac8_month_lengths_from_calendar(
    year: int,
    month: int,
    as_of_day: int,
    spent: Decimal,
    expected_rate: Decimal,
    expected_projected: Decimal,
) -> None:
    """AC5-AC8: длина месяца 28/29/30/31 берётся из calendar.monthrange."""
    result = forecast_month(spent, year, month, date(year, month, as_of_day))
    assert result["days_in_month"] == calendar_math.days_in_month(year, month)
    assert result["daily_rate"] == expected_rate
    assert result["projected_total"] == expected_projected


def test_ac9_whole_month_pace() -> None:
    """AC9 Режим WHOLE_MONTH: 600 за 15 дней октября -> rate 40.00, projected 1240.00."""
    result = forecast_month(Decimal("600.00"), 2026, 10, date(2026, 10, 15), pace=WHOLE_MONTH)
    assert result["pace"] == "WHOLE_MONTH"
    assert result["daily_rate"] == Decimal("40.00")
    assert result["projected_total"] == Decimal("1240.00")


def test_ac10_recent_window_pace() -> None:
    """AC10 Режим RECENT_WINDOW(7): те же 600, из них 490 за 7 дней -> rate 70.00, 1720.00."""
    result = forecast_month(
        Decimal("600.00"),
        2026,
        10,
        date(2026, 10, 15),
        pace=RECENT_WINDOW,
        recent_window_total=Decimal("490.00"),
    )
    assert result["pace"] == "RECENT_WINDOW"
    assert result["daily_rate"] == Decimal("70.00")
    assert result["projected_total"] == Decimal("1720.00")


def test_ac11_rounding_half_up_once_at_the_end() -> None:
    """AC11 Округление: 1/3 темпа не округляется до остатка; половина копейки вверх."""
    result = forecast_month(Decimal("100.00"), 2026, 10, date(2026, 10, 3))
    assert result["daily_rate"] == Decimal("33.33")
    assert result["projected_total"] == Decimal("1033.33")

    extra = forecast_month(
        Decimal("0.00"), 2026, 10, date(2026, 10, 15), extra_known_amounts=Decimal("0.125")
    )
    assert extra["projected_total"] == Decimal("0.13")


def test_ac12_future_month_divides_nothing() -> None:
    """AC12 Будущий месяц: as_of до начала -> days_elapsed=0, без ZeroDivisionError."""
    result = forecast_month(Decimal("0.00"), 2026, 10, date(2026, 9, 30))
    assert result["days_elapsed"] == 0
    assert result["daily_rate"] == Decimal("0.00")
    assert result["projected_total"] == Decimal("0.00")
    assert result["low_confidence"] is True


def test_forecast_zero_days_elapsed_direct_call() -> None:
    """Защитная ветка спецификации: linear_forecast с days_elapsed=0 без деления на ноль."""
    assert linear_forecast(Decimal("100.00"), 0, 31) == Decimal("100.00")


def test_forecast_recent_window_limits_window_on_first_day() -> None:
    """Окно RECENT_WINDOW ограничено days_elapsed: в первый день делим на 1, не на 7."""
    result = forecast_month(
        Decimal("10.00"),
        2026,
        10,
        date(2026, 10, 1),
        pace=RECENT_WINDOW,
        recent_window_total=Decimal("10.00"),
    )
    assert result["daily_rate"] == Decimal("10.00")
    assert result["projected_total"] == Decimal("310.00")


def test_forecast_low_confidence_border_is_three_days() -> None:
    """low_confidence: days_elapsed 2 -> True, 3 -> False."""
    second_day = forecast_month(Decimal("0.00"), 2026, 10, date(2026, 10, 2))
    assert second_day["low_confidence"] is True
    third_day = forecast_month(Decimal("0.00"), 2026, 10, date(2026, 10, 3))
    assert third_day["low_confidence"] is False


def test_forecast_results_are_decimals_not_floats() -> None:
    """S6.2: внутри ядра нет перехода на float; итоги возвращаются Decimal."""
    result = forecast_month(Decimal("600.00"), 2026, 10, date(2026, 10, 15))
    for key in ("spent_to_date", "daily_rate", "projected_total"):
        assert isinstance(result[key], Decimal), key


def test_money_rounds_half_up() -> None:
    """money(): половина копейки вверх, включая отрицательные суммы."""
    assert money(Decimal("0.125")) == Decimal("0.13")
    assert money(Decimal("25.505")) == Decimal("25.51")
    assert money(Decimal("-25.505")) == Decimal("-25.51")


@pytest.mark.parametrize(
    ("month", "expected_days"),
    list(enumerate([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31], start=1)),
    ids=[f"2026-{month:02d}" for month in range(1, 13)],
)
def test_forecast_days_in_month_all_twelve_months(month: int, expected_days: int) -> None:
    """Длина месяца по календарю для всех 12 месяцев 2026 года."""
    assert calendar_math.days_in_month(2026, month) == expected_days


def test_forecast_days_in_month_handles_leap_february() -> None:
    """Високосный февраль 29, обычный 28: monthrange, а не константа."""
    assert calendar_math.days_in_month(2028, 2) == 29
    assert calendar_math.days_in_month(2027, 2) == 28
