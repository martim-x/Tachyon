"""HTML-страницы дашборда пользователя (docs/03 §S8.1, задача TT-33).

Слой interface: здесь только разбор запроса и рендеринг шаблона Jinja2.
Данные страницы приходят из доменных служб без второй копии агрегации
(NFR-3: единая функция агрегации TT-26):

- сводка месяца, категории и прогноз - один вызов ReportingService.monthly,
  тот же код, что отдаёт /api/v1/reports/monthly;
- список последних операций с фильтрами по дате, категории и типу -
  OperationService.list_page (ScopedRepository, user_id из UserContext);
- выпадающий список категорий - CategoryService.list;
- диаграмма расходов - компонент TT-29 (app/interface/dashboard,
  MR !31): render_category_chart получает точки той же агрегации
  ReportingService.by_category за выбранный период; свой рендеринг
  диаграммы здесь не дублируется.

Деньги выводятся в шаблон только строками Decimal.quantize("0.01")
ROUND_HALF_UP (docs/02 §«Правила денег»).

Шаблоны страниц лежат в app/interface/api/templates/ (docs/02
§«Структура папок», слой interface). Шаблон компонента диаграммы
app/interface/templates/reporting/category_chart.html рендерится
собственным окружением app/interface/dashboard/rendering.py и
встраивается в страницу готовым фрагментом.
"""

import calendar
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import model_validator as pydantic_model_validator
from starlette import status as http_status
from starlette.responses import Response

from app.core.config import get_settings
from app.core.errors import AuthenticationFailed
from app.domains.identity.repository import UserRepository
from app.domains.identity.service import IdentityService, create_access_token
from app.domains.ledger.models import Category, Operation
from app.domains.ledger.repository import OperationRepository
from app.domains.ledger.schemas import OperationListQuery
from app.domains.ledger.service import CategoryService, OperationService
from app.domains.reporting.service import ReportingService
from app.interface.api.deps import ClockDep, CurrentUser, SessionDep
from app.interface.api.schemas import error_responses
from app.interface.dashboard import render_category_chart

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


class DashboardFilters(OperationListQuery):
    """Фильтры HTML-формы дашборда: те же поля, что у GET /api/v1/operations.

    Браузерная форма всегда отсылает все свои поля: незаполненное поле
    приходит пустой строкой, а не отсутствует в запросе. Для фильтров
    пустая строка означает «не задан», поэтому она превращается в None
    до доменной валидации (Duo review !29: иначе запрос формы
    GET /dashboard?from=&to=&… даёт 422 JSON вместо HTML-страницы).
    Правило порядка дат и остальные правила остаются в родительской
    OperationListQuery — второй копии правил валидации нет.
    """

    @pydantic_model_validator(mode="before")
    @classmethod
    def _empty_form_fields_are_unset(cls, data: object) -> object:
        if not isinstance(data, dict) or not data:
            return data
        values = dict(data)
        for name in ("date_from", "date_to", "category_id", "kind"):
            field = cls.model_fields[name]
            for key in (name, field.alias or name):
                if values.get(key) == "":
                    values[key] = None
        return values


router = APIRouter(tags=["Дашборд"])


@router.get(
    "/login",
    response_class=HTMLResponse,
    include_in_schema=False,
    summary="Страница входа",
)
async def login_page(request: Request) -> HTMLResponse:
    """Показать форму входа в браузерную сессию."""
    return templates.TemplateResponse(
        request,
        "login.html",
        {"error": None},
    )


@router.post(
    "/login",
    include_in_schema=False,
    summary="Вход в браузерную сессию",
)
async def login_submit(
    request: Request,
    session: SessionDep,
    email: str = Form(...),
    password: str = Form(...),
) -> Response:
    """Проверить учётные данные, выдать cookie и редиректить на дашборд."""
    service = IdentityService(UserRepository(session))
    try:
        user = await service.authenticate(email=email, password=password)
    except AuthenticationFailed:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Неверный email или пароль"},
            status_code=http_status.HTTP_401_UNAUTHORIZED,
        )

    token = create_access_token(user.id)
    settings = get_settings()
    response = RedirectResponse(
        url="/dashboard",
        status_code=http_status.HTTP_303_SEE_OTHER,
    )
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=settings.token_ttl * 60,
        path="/",
    )
    return response


@router.get(
    "/logout",
    include_in_schema=False,
    summary="Выход из браузерной сессии",
)
async def logout() -> Response:
    """Удалить cookie сессии и вернуться на страницу входа."""
    response = RedirectResponse(
        url="/login",
        status_code=http_status.HTTP_303_SEE_OTHER,
    )
    response.delete_cookie(key="access_token", path="/")
    return response


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


@router.get(
    "/dashboard",
    response_class=HTMLResponse,
    summary="Страница дашборда",
    responses={
        200: {
            "description": "HTML-страница дашборда за текущий месяц.",
            "content": {"text/html": {"schema": {"type": "string"}}},
        },
        **error_responses(
            401,
            422,
            content={
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                }
            },
        ),
    },
)
async def dashboard_page(
    query: Annotated[DashboardFilters, Query()],
    request: Request,
    current_user: CurrentUser,
    session: SessionDep,
    clock: ClockDep,
) -> Response:
    """HTML-дашборд: сводка текущего месяца и последние операции с фильтрами.

    Сводка это месячный отчёт за текущий месяц (доходы, расходы, остаток
    и прогноз на месяц, docs/03 §S8.1 T1): один вызов ReportingService.monthly
    по часам ClockDep. Фильтры последнего блока операций - поля
    DashboardFilters (наследует OperationListQuery, как у GET /api/v1/
    operations); те же даты задают период диаграммы TT-29, поэтому при
    смене периода компонент рендерится заново (docs/03 §S10.1). Анонимный
    запрос получает 401 от зависимости CurrentUser, как у остального API.
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

    chart_from = query.date_from if query.date_from is not None else month_start
    chart_to = query.date_to if query.date_to is not None else month_last
    chart_points = await ReportingService(session).by_category(
        date_from=chart_from,
        date_to=chart_to,
    )

    context = {
        "user_email": current_user.email,
        "report_month": report.forecast_month,
        "summary": {
            "income": report.income,
            "expense": report.expense,
            "balance": report.balance,
            "forecast": report.forecast,
        },
        "chart_html": render_category_chart(
            chart_points,
            date_from=chart_from,
            date_to=chart_to,
        ),
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
