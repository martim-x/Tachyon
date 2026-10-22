"""Сервис отчётов: период, pandas-агрегация и прогноз."""

import calendar
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, SystemClock
from app.core.errors import ValidationError
from app.domains.forecasting.service import (
    forecast_month as calculate_forecast_month,
)
from app.domains.reporting.queries import (
    CategoryAggregate,
    ReportAggregate,
    aggregate_report,
)
from app.domains.reporting.repository import ReportingRepository
from app.domains.reporting.schemas import ReportDTO, SeriesPointDTO


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

    При равенстве выбирается более поздний месяц — он ближе к текущему
    состоянию пользователя и полезнее для прогноза.
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

    current_month = date(
        date_from.year,
        date_from.month,
        1,
    )
    candidates: list[tuple[int, date]] = []

    while current_month <= date_to:
        overlap_start = max(date_from, current_month)
        overlap_end = min(date_to, month_end(current_month))

        overlap_days = (overlap_end - overlap_start).days + 1
        candidates.append((overlap_days, current_month))

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
