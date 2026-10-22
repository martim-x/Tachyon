"""HTTP API аналитических отчётов."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.domains.reporting.schemas import ReportDTO, SeriesPointDTO
from app.domains.reporting.service import ReportingService
from app.interface.api.deps import CurrentUser, SessionDep

router = APIRouter(
    prefix="/api/v1/reports",
    tags=["Отчёты"],
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
) -> ReportDTO:
    service = ReportingService(session)
    return await service.monthly(
        date_from=date_from,
        date_to=date_to,
    )


@router.get(
    "/by-category",
    response_model=list[SeriesPointDTO],
    summary="Получить расходы по категориям",
    description=("Возвращает суммы, процентные доли и сравнение с лимитами."),
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
