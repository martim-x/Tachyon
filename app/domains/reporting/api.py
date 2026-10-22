"""HTTP API аналитических отчётов (docs/02 §reporting, docs/03 §S6.5)."""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.core.errors import ValidationError
from app.domains.forecasting.schemas import ForecastDTO
from app.domains.forecasting.strategies import RECENT_WINDOW, WHOLE_MONTH
from app.domains.reporting.schemas import ReportDTO, SeriesPointDTO
from app.domains.reporting.service import ReportingService
from app.interface.api.deps import ClockDep, CurrentUser, ExportDep, SessionDep

router = APIRouter(
    prefix="/api/v1/reports",
    tags=["Отчёты"],
)

forecast_router = APIRouter(
    prefix="/api/v1",
    tags=["Прогноз"],
)

DateFrom = Annotated[
    date,
    Query(
        alias="from",
        description="Начало отчётного периода включительно",
        examples=["2026-10-01"],
    ),
]

DateTo = Annotated[
    date,
    Query(
        alias="to",
        description="Конец отчётного периода включительно",
        examples=["2026-10-31"],
    ),
]


@router.get(
    "/monthly",
    response_model=ReportDTO,
    summary="Получить финансовый отчёт",
    description=(
        "Возвращает доходы, расходы, баланс, категории и прогноз "
        "для месяца, содержащего большую часть периода."
    ),
)
async def monthly_report(
    date_from: DateFrom,
    date_to: DateTo,
    _current_user: CurrentUser,
    session: SessionDep,
    clock: ClockDep,
) -> ReportDTO:
    service = ReportingService(session, clock=clock)
    return await service.monthly(
        date_from=date_from,
        date_to=date_to,
    )


@router.get(
    "/by-category",
    response_model=list[SeriesPointDTO],
    summary="Получить расходы по категориям",
    description=(
        "Возвращает суммы, процентные доли и сравнение с лимитами."
    ),
)
async def report_by_category(
    date_from: DateFrom,
    date_to: DateTo,
    _current_user: CurrentUser,
    session: SessionDep,
) -> list[SeriesPointDTO]:
    service = ReportingService(session)
    return await service.by_category(
        date_from=date_from,
        date_to=date_to,
    )


ExportFormat = Literal["excel", "xlsx"]


@router.get(
    "/monthly/export",
    summary="Выгрузить отчёт за период в Excel",
    description=(
        "Файл xlsx с листами «Операции», «По категориям» и «Сводка»: "
        "данные собирает та же агрегация домена, что и monthly (NFR-3), "
        "формат файла - адаптер app.interface.export (docs/03 §S7.1)."
    ),
)
async def export_monthly_report(
    date_from: DateFrom,
    date_to: DateTo,
    _current_user: CurrentUser,
    session: SessionDep,
    exporter: ExportDep,
    export_format: Annotated[
        ExportFormat,
        Query(
            alias="format",
            description="Формат файла выгрузки",
        ),
    ] = "excel",
) -> Response:
    service = ReportingService(session)
    report = await service.export_payload(
        date_from=date_from,
        date_to=date_to,
    )

    file = exporter.export(report)

    return Response(
        content=file.content,
        media_type=file.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{file.filename}"',
        },
    )


# Границы года, которые понимает datetime.date: 0000 и 10000 - вне диапазона.
# Регулярка `\d{4}-\d{2}` их пропускает, поэтому граница проверяется явно.
# Верхняя граница - 9998, а не 9999: для декабря считается следующий месяц
# через date(year + 1, 1, 1), а 9999-12 уводит в год 10000 и роняет date().
MIN_YEAR = 1
MAX_YEAR = 9998


@forecast_router.get(
    "/forecast",
    response_model=ForecastDTO,
    summary="Прогноз расходов на месяц",
    description=(
        "Месяц задаётся строкой YYYY-MM. Месяц, который ещё не начался — "
        "это 200 с нулями и low_confidence, а не 404 (docs/06 §Нулевые траты)."
    ),
)
async def forecast_report(
    month: Annotated[
        str,
        Query(pattern=r"^\d{4}-\d{2}$", description="Месяц прогноза в формате YYYY-MM"),
    ],
    _current_user: CurrentUser,
    session: SessionDep,
    clock: ClockDep,
    pace: Annotated[
        str,
        Query(pattern=r"^(WHOLE_MONTH|RECENT_WINDOW)$", description="Режим темпа"),
    ] = "WHOLE_MONTH",
) -> ForecastDTO:
    try:
        year_text, month_text = month.split("-")
        year = int(year_text)
        month_number = int(month_text)
    except ValueError as exc:
        raise ValidationError(
            detail=[{"field": "month", "issue": "month должен быть в формате YYYY-MM"}]
        ) from exc

    if not 1 <= month_number <= 12:
        raise ValidationError(
            detail=[{"field": "month", "issue": "month должен быть от 01 до 12"}]
        )
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise ValidationError(
            detail=[{"field": "year", "issue": "year должен быть от 0001 до 9998"}]
        )

    pace_strategy = RECENT_WINDOW if pace == "RECENT_WINDOW" else WHOLE_MONTH

    month_start = date(year, month_number, 1)

    service = ReportingService(session, clock=clock)
    return await service.forecast(month_start=month_start, pace=pace_strategy)