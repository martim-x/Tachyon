"""Сервис отчётов: период, pandas-агрегация и прогноз."""

import calendar
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, SystemClock
from app.core.errors import ValidationError
from app.domains.forecasting.calendar_math import days_elapsed as elapsed_days
from app.domains.forecasting.schemas import ForecastDTO
from app.domains.forecasting.service import (
    forecast_month as calculate_forecast_month,
)
from app.domains.forecasting.strategies import RECENT_WINDOW, WHOLE_MONTH, PaceStrategy
from app.domains.reporting.queries import (
    CategoryAggregate,
    ReportAggregate,
    aggregate_report,
)
from app.domains.reporting.repository import ReportingRepository
from app.domains.reporting.schemas import ReportDTO, SeriesPointDTO

MAX_REPORT_PERIOD_DAYS = 366 * 5


def month_end(month_start: date) -> date:
    """Последний календарный день месяца."""

    last_day = calendar.monthrange(
        month_start.year,
        month_start.month,
    )[1]
    return date(
        month_start.year,
        month_start.month,
        last_day,
    )


def next_month(month_start: date) -> date:
    """Первый день следующего месяца."""

    if month_start.month == 12:
        return date(month_start.year + 1, 1, 1)

    return date(
        month_start.year,
        month_start.month + 1,
        1,
    )


def dominant_month(date_from: date, date_to: date) -> date:
    """Выбрать месяц, содержащий наибольшее число дней периода.

    При равенстве выбирается более поздний месяц. Период ограничен пятью
    годами, чтобы один запрос не загружал слишком много данных в память.
    """

    if date_from > date_to:
        raise ValidationError(
            detail=[
                {
                    "field": "from",
                    "issue": "from не может быть позже to",
                }
            ]
        )

    period_days = (date_to - date_from).days + 1
    if period_days > MAX_REPORT_PERIOD_DAYS:
        raise ValidationError(
            detail=[
                {
                    "field": "to",
                    "issue": "Период отчёта не может превышать 5 лет",
                }
            ]
        )

    current_month = date(
        date_from.year,
        date_from.month,
        1,
    )
    candidates: list[tuple[int, date]] = []

    while True:
        overlap_start = max(date_from, current_month)
        overlap_end = min(date_to, month_end(current_month))

        overlap_days = (overlap_end - overlap_start).days + 1
        candidates.append((overlap_days, current_month))

        # Не вызываем next_month после декабря 9999 и после последнего
        # месяца запрошенного периода.
        if current_month.year == date_to.year and current_month.month == date_to.month:
            break

        current_month = next_month(current_month)

    return max(
        candidates,
        key=lambda item: (item[0], item[1]),
    )[1]


def to_series_point(
    category: CategoryAggregate,
) -> SeriesPointDTO:
    """Преобразовать результат общей агрегации в API DTO."""

    return SeriesPointDTO(
        category_id=category.category_id,
        category_name=category.category_name,
        amount=category.amount,
        share_percent=category.share_percent,
        limit=category.limit,
        limit_remaining=category.limit_remaining,
        limit_percent=category.limit_percent,
        limit_exceeded=category.limit_exceeded,
    )


class ReportingService:
    """Read-only построение месячного и категорийного отчётов."""

    def __init__(
        self,
        session: AsyncSession,
        clock: Clock | None = None,
    ) -> None:
        self._repository = ReportingRepository(session)
        self._clock = clock or SystemClock()

    async def aggregate_period(
        self,
        *,
        date_from: date,
        date_to: date,
    ) -> tuple[ReportAggregate, date]:
        """Единая агрегация для API, экспорта и диаграммы."""

        selected_month = dominant_month(date_from, date_to)

        rows = await self._repository.period_rows(
            date_from=date_from,
            date_to=date_to,
            limit_month=selected_month,
        )

        return aggregate_report(rows), selected_month

    async def monthly(
        self,
        *,
        date_from: date,
        date_to: date,
    ) -> ReportDTO:
        """Полный отчёт: итоги, категории и прогноз."""

        aggregate, selected_month = await self.aggregate_period(
            date_from=date_from,
            date_to=date_to,
        )

        today = self._clock.today()
        selected_month_end = month_end(selected_month)

        if today < selected_month:
            forecast_aggregate = aggregate_report([])
        else:
            forecast_date_to = min(today, selected_month_end)
            forecast_rows = await self._repository.period_rows(
                date_from=selected_month,
                date_to=forecast_date_to,
                limit_month=selected_month,
            )
            forecast_aggregate = aggregate_report(forecast_rows)

        forecast_data = calculate_forecast_month(
            spent_to_date=forecast_aggregate.expense,
            year=selected_month.year,
            month=selected_month.month,
            as_of=today,
        )
        projected_total = forecast_data["projected_total"]

        if not isinstance(projected_total, Decimal):
            raise TypeError("Прогноз должен возвращать Decimal")

        return ReportDTO(
            date_from=date_from,
            date_to=date_to,
            income=aggregate.income,
            expense=aggregate.expense,
            balance=aggregate.balance,
            categories=[to_series_point(category) for category in aggregate.categories],
            forecast=projected_total,
            forecast_month=selected_month.strftime("%Y-%m"),
            forecast_basis="dominant_period_month",
        )

    async def by_category(
        self,
        *,
        date_from: date,
        date_to: date,
    ) -> list[SeriesPointDTO]:
        """Категорийные данные для таблицы или диаграммы."""

        aggregate, _selected_month = await self.aggregate_period(
            date_from=date_from,
            date_to=date_to,
        )

        return [to_series_point(category) for category in aggregate.categories]

    async def forecast(
        self,
        *,
        month_start: date,
        pace: PaceStrategy = WHOLE_MONTH,
    ) -> ForecastDTO:
        """Прогноз расходов на месяц (docs/03 §S6.5 T1, docs/06 §Формулы).

        Месяц задаётся целиком: траты берутся с 1-го числа месяца по
        отчётную дату (min(сегодня, конец месяца)). Это окно совпадает
        с прогнозом в monthly-отчёте (NFR-3: одна функция агрегации).

        Месяц, который ещё не начался — это 200 с нулями и
        low_confidence, а не 404 (docs/06 §Нулевые траты).
        """
        today = self._clock.today()
        month_last = month_end(month_start)
        report_day = min(today, month_last)

        if today < month_start:
            spent_to_date = Decimal("0.00")
            recent_window_total = Decimal("0.00")
        else:
            rows = await self._repository.period_rows(
                date_from=month_start,
                date_to=report_day,
                limit_month=month_start,
            )
            spent_to_date = aggregate_report(rows).expense

            if pace is RECENT_WINDOW:
                days_elapsed = elapsed_days(month_start.year, month_start.month, today)
                window_days = min(7, days_elapsed)
                if window_days > 0:
                    window_start = report_day - timedelta(days=window_days - 1)
                    if window_start < month_start:
                        window_start = month_start
                    window_rows = await self._repository.period_rows(
                        date_from=window_start,
                        date_to=report_day,
                        limit_month=month_start,
                    )
                    recent_window_total = aggregate_report(window_rows).expense
                else:
                    recent_window_total = Decimal("0.00")
            else:
                recent_window_total = Decimal("0.00")

        data = calculate_forecast_month(
            spent_to_date=spent_to_date,
            year=month_start.year,
            month=month_start.month,
            as_of=today,
            pace=pace,
            recent_window_total=recent_window_total,
        )

        low_confidence = bool(data["low_confidence"]) or spent_to_date == Decimal("0.00")

        return ForecastDTO(
            year=month_start.year,
            month=month_start.month,
            pace=data["pace"],
            days_in_month=data["days_in_month"],
            days_elapsed=data["days_elapsed"],
            days_remaining=data["days_remaining"],
            spent_to_date=data["spent_to_date"],
            daily_rate=data["daily_rate"],
            projected_total=data["projected_total"],
            low_confidence=low_confidence,
        )
