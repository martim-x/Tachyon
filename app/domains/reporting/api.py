"""HTTP API аналитических отчётов и прогноза."""

from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.core.errors import ValidationError
from app.domains.forecasting.schemas import ForecastDTO
from app.domains.forecasting.strategies import (
    RECENT_WINDOW,
    WHOLE_MONTH,
)
from app.domains.reporting.schemas import (
    ReportDTO,
    SeriesPointDTO,
)
from app.domains.reporting.service import ReportingService
from app.interface.api.deps import (
    ClockDep,
    CurrentUser,
    ExportDep,
    SessionDep,
)
from app.interface.api.schemas import error_responses

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
        description="Начало отчётного периода включительно.",
        examples=["2026-10-01"],
    ),
]

DateTo = Annotated[
    date,
    Query(
        alias="to",
        description="Конец отчётного периода включительно.",
        examples=["2026-10-31"],
    ),
]

ExportFormat = Literal[
    "excel",
    "xlsx",
]

ForecastPace = Literal[
    "WHOLE_MONTH",
    "RECENT_WINDOW",
]

EXPORT_RESPONSES: dict[
    int | str,
    dict[str, Any],
] = {
    200: {
        "description": "Отчёт успешно сформирован.",
        "content": {
            ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"): {
                "schema": {
                    "type": "string",
                    "format": "binary",
                }
            }
        },
    },
    **error_responses(401, 422),
}


@router.get(
    "/monthly",
    response_model=ReportDTO,
    summary="Получить финансовый отчёт",
    description=(
        "Возвращает доходы, расходы, баланс, категории и прогноз "
        "за указанный период. Для прогноза используется месяц, "
        "содержащий большую часть выбранного периода."
    ),
    responses=error_responses(401, 422),
)
async def monthly_report(
    date_from: DateFrom,
    date_to: DateTo,
    _current_user: CurrentUser,
    session: SessionDep,
    clock: ClockDep,
) -> ReportDTO:
    service = ReportingService(
        session,
        clock=clock,
    )
    return await service.monthly(
        date_from=date_from,
        date_to=date_to,
    )


@router.get(
    "/by-category",
    response_model=list[SeriesPointDTO],
    summary="Получить расходы по категориям",
    description=(
        "Возвращает суммы расходов, процентные доли категорий "
        "и сравнение с бюджетными лимитами. Операции без категории "
        "попадают в группу «Без категории»."
    ),
    responses=error_responses(401, 422),
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


@router.get(
    "/monthly/export",
    response_class=Response,
    summary="Выгрузить финансовый отчёт",
    description=(
        "Формирует Excel-файл за указанный период. "
        "Файл содержит листы «Операции», «По категориям» "
        "и «Сводка» и использует ту же агрегацию, "
        "что и обычный месячный отчёт."
    ),
    responses=EXPORT_RESPONSES,
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
            description=("Формат Excel-файла. Значения excel и xlsx являются эквивалентными."),
            examples=["xlsx"],
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
            "Content-Disposition": (f'attachment; filename="{file.filename}"'),
        },
    )


# Границы, поддерживаемые datetime.date.
# Верхняя граница 9998 нужна для безопасного вычисления следующего года.
MIN_YEAR = 1
MAX_YEAR = 9998


@forecast_router.get(
    "/forecast",
    response_model=ForecastDTO,
    summary="Получить прогноз расходов",
    description=(
        "Рассчитывает прогноз расходов для месяца YYYY-MM. "
        "Для ещё не начавшегося месяца возвращаются нулевые значения "
        "и признак низкой достоверности, а не ошибка 404."
    ),
    responses=error_responses(401, 422),
)
async def forecast_report(
    month: Annotated[
        str,
        Query(
            pattern=r"^\d{4}-\d{2}$",
            description="Месяц прогноза в формате YYYY-MM.",
            examples=["2026-10"],
        ),
    ],
    _current_user: CurrentUser,
    session: SessionDep,
    clock: ClockDep,
    pace: Annotated[
        ForecastPace,
        Query(
            description=(
                "Стратегия расчёта темпа: весь прошедший месяц или последнее доступное окно."
            ),
            examples=["WHOLE_MONTH"],
        ),
    ] = "WHOLE_MONTH",
) -> ForecastDTO:
    try:
        year_text, month_text = month.split("-")
        year = int(year_text)
        month_number = int(month_text)
    except ValueError as exc:
        raise ValidationError(
            detail=[
                {
                    "field": "month",
                    "issue": ("month должен быть в формате YYYY-MM"),
                }
            ]
        ) from exc

    if not 1 <= month_number <= 12:
        raise ValidationError(
            detail=[
                {
                    "field": "month",
                    "issue": "month должен быть от 01 до 12",
                }
            ]
        )

    if not MIN_YEAR <= year <= MAX_YEAR:
        raise ValidationError(
            detail=[
                {
                    "field": "year",
                    "issue": "year должен быть от 0001 до 9998",
                }
            ]
        )

    pace_strategy = RECENT_WINDOW if pace == "RECENT_WINDOW" else WHOLE_MONTH
    month_start = date(
        year,
        month_number,
        1,
    )

    service = ReportingService(
        session,
        clock=clock,
    )
    return await service.forecast(
        month_start=month_start,
        pace=pace_strategy,
    )
