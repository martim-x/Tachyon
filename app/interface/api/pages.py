"""HTML-страницы дашборда пользователя (docs/03 §S8.1, задача TT-33).

Слой interface: здесь только разбор запроса и рендеринг шаблона Jinja2.
Данные страницы приходят из доменных служб без второй копии агрегации
(NFR-3: единая функция агрегации TT-26):

- сводка месяца, категории и прогноз - один вызов ReportingService.monthly,
  тот же код, что отдаёт /api/v1/reports/monthly;
- список последних операций с фильтрами по дате, категории и типу -
  OperationService.list_page (ScopedRepository, user_id из UserContext);
- выпадающий список категорий - CategoryService.list.

Деньги выводятся в шаблон только строками Decimal.quantize("0.01")
ROUND_HALF_UP (docs/02 §«Правила денег»).

Шаблоны страниц лежат в app/interface/api/templates/ (docs/02
§«Структура папок», слой interface). Компонент диаграммы расходов - зона
TT-29: его файл templates/dashboard/chart.html подключается через
{% include ... ignore missing %}, пока файла нет, страница рендерится
без диаграммы. Своего роутера дашбордовой диаграмме не нужно: данные
доступны через /api/v1/reports/by-category.
"""

import calendar
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from app.domains.ledger.models import Category, Operation
from app.domains.ledger.repository import OperationRepository
from app.domains.ledger.schemas import OperationListQuery
from app.domains.ledger.service import CategoryService, OperationService
from app.domains.reporting.service import ReportingService
from app.interface.api.deps import ClockDep, CurrentUser, SessionDep

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

router = APIRouter(tags=["Дашборд"])


def _money(value: Decimal) -> str:
    """Деньги для шаблона: строка с двумя знаками, округление половины вверх."""

    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


templates = Jinja2Templates(directory=TEMPLATES_DIR)
# money - единственная денежная конвенция шаблонов: Decimal -> строка 0.01.
templates.env.filters["money"] = _money


def _day_label(value: datetime) -> str:
    """Дата операции в строке таблицы: календарный день UTC.

    SQLite теряет смещение при записи DateTime(timezone=True); сервис
    нормализует моменты в UTC, поэтому наивные значения читаются как UTC.
    """

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%d")


def _operation_row(operation: Operation, names: dict[UUID, str]) -> dict[str, object]:
    """Строка таблицы последних операций для шаблона.

    Сумма остаётся Decimal до самого рендеринга: строку с двумя знаками
    даёт шаблонный фильтр money, здесь сырые копейки читаются только
    через границу денег OperationRepository.to_money (docs/02).
    """

    return {
        "occurred_at": _day_label(operation.occurred_at),
        "category": names.get(operation.category_id, "Без категории"),
        "kind": operation.kind,
        "kind_label": "Доход" if operation.kind == "income" else "Расход",
        "amount": OperationRepository.to_money(operation).amount,
        "note": operation.note or "",
    }


def _category_option(category: Category) -> dict[str, str]:
    """Пара для выпадающего списка: строковый id и имя категории."""

    return {"id": str(category.id), "name": category.name}


@router.get("/dashboard", summary="Страница дашборда")
async def dashboard_page(
    query: Annotated[OperationListQuery, Query()],
    request: Request,
    current_user: CurrentUser,
    session: SessionDep,
    clock: ClockDep,
) -> Response:
    """HTML-дашборд: сводка текущего месяца и последние операции с фильтрами.

    Сводка это месячный отчёт за текущий месяц (доходы, расходы, остаток
    и прогноз на месяц, docs/03 §S8.1 T1): один вызов ReportingService.monthly
    по часам ClockDep. Фильтры последнего блока операций - поля
    OperationListQuery, как у GET /api/v1/operations. Анонимный запрос
    получает 401 от зависимости CurrentUser, как у остального API.
    """

    today = clock.today()
    month_start = date(today.year, today.month, 1)
    month_last = date(
        today.year,
        today.month,
        calendar.monthrange(today.year, today.month)[1],
    )

    report = await ReportingService(session, clock=clock).monthly(
        date_from=month_start,
        date_to=month_last,
    )

    operations, total = await OperationService(session).list_page(query)
    categories: Sequence[Category] = await CategoryService(session).list()
    names: dict[UUID, str] = {category.id: category.name for category in categories}

    context = {
        "user_email": current_user.email,
        "report_month": report.forecast_month,
        "summary": {
            "income": report.income,
            "expense": report.expense,
            "balance": report.balance,
            "forecast": report.forecast,
        },
        "operations": [_operation_row(operation, names) for operation in operations],
        "total": total,
        "page": query.page,
        "limit": query.limit,
        "categories": [_category_option(category) for category in categories],
        "filters": {
            "date_from": query.date_from.isoformat() if query.date_from else "",
            "date_to": query.date_to.isoformat() if query.date_to else "",
            "category_id": str(query.category_id) if query.category_id else "",
            "kind": query.kind or "",
        },
    }

    return templates.TemplateResponse(request, "dashboard.html", context)
