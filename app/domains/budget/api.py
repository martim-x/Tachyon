"""HTTP API бюджетных лимитов."""

from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.errors import Conflict, NotFound
from app.domains.budget.models import BudgetLimit
from app.domains.budget.schemas import (
    LimitCreate,
    LimitRead,
    LimitStatusDTO,
)
from app.domains.budget.service import limit_status
from app.domains.forecasting.service import forecast_month
from app.domains.ledger.models import Category, Operation
from app.interface.api.deps import (
    ClockDep,
    CurrentUser,
    SessionDep,
)
from app.interface.api.schemas import error_responses

router = APIRouter(
    prefix="/api/v1/budget-limits",
    tags=["Бюджет"],
)

CategoryId = Annotated[
    UUID,
    Path(
        description="Идентификатор категории, для которой установлен лимит.",
    ),
]

MonthQuery = Annotated[
    date,
    Query(
        description=(
            "Месяц действия лимита. Допускается любая дата месяца; "
            "она нормализуется к первому числу."
        ),
        examples=["2026-10-01"],
    ),
]

LimitAmountQuery = Annotated[
    int,
    Query(
        gt=0,
        description="Новый размер лимита в целых копейках.",
        examples=[500000],
    ),
]


def normalize_month(value: date) -> date:
    """Привести любую дату к первому дню её месяца."""

    return value.replace(day=1)


def next_month(month: date) -> date:
    """Получить первый день следующего месяца."""

    if month.month == 12:
        return date(month.year + 1, 1, 1)

    return date(
        month.year,
        month.month + 1,
        1,
    )


def day_start(day: date) -> datetime:
    """Получить начало календарного дня в UTC."""

    return datetime(
        day.year,
        day.month,
        day.day,
        tzinfo=UTC,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=LimitRead,
    summary="Создать бюджетный лимит",
    description=(
        "Создаёт месячный лимит расходов для категории текущего пользователя. "
        "Для одной категории допускается только один лимит на месяц."
    ),
    responses=error_responses(401, 404, 409, 422),
)
async def create_limit(
    payload: LimitCreate,
    current_user: CurrentUser,
    session: SessionDep,
):
    category_stmt = select(Category).where(
        Category.id == payload.category_id,
        Category.user_id == current_user.id,
    )
    category_result = await session.execute(category_stmt)
    category = category_result.scalar_one_or_none()

    if category is None:
        raise NotFound("Категория бюджетного лимита не найдена")

    statement = select(BudgetLimit).where(
        BudgetLimit.user_id == current_user.id,
        BudgetLimit.category_id == payload.category_id,
        BudgetLimit.month == payload.month,
    )
    result = await session.execute(statement)
    existing = result.scalar_one_or_none()

    if existing is not None:
        raise Conflict(
            "Бюджетный лимит уже существует",
            safe_message="Лимит уже существует",
        )

    new_limit = BudgetLimit(
        user_id=current_user.id,
        **payload.model_dump(),
    )
    session.add(new_limit)

    try:
        await session.flush()
    except IntegrityError as exc:
        # Это исключение также закрывает гонку двух одновременных запросов.
        # session_scope выполнит rollback после выхода с исключением.
        raise Conflict(
            "Нарушено ограничение уникальности бюджетного лимита",
            safe_message="Лимит уже существует",
        ) from exc

    return new_limit


@router.get(
    "",
    response_model=list[LimitRead],
    summary="Получить бюджетные лимиты",
    description=(
        "Возвращает все бюджетные лимиты текущего пользователя. "
        "Если лимитов нет, возвращается пустой список."
    ),
    responses=error_responses(401),
)
async def limits_list(
    current_user: CurrentUser,
    session: SessionDep,
):
    statement = select(BudgetLimit).where(
        BudgetLimit.user_id == current_user.id,
    )
    result = await session.execute(statement)

    return result.scalars().all()


@router.put(
    "/{category_id}",
    response_model=LimitRead,
    summary="Изменить бюджетный лимит",
    description=(
        "Изменяет размер лимита для категории и указанного месяца. "
        "Чужой или несуществующий лимит возвращает одинаковую ошибку 404."
    ),
    responses=error_responses(401, 404, 422),
)
async def update_limit(
    category_id: CategoryId,
    month: MonthQuery,
    limit_amount_cents: LimitAmountQuery,
    current_user: CurrentUser,
    session: SessionDep,
):
    normalized_month = normalize_month(month)

    statement = select(BudgetLimit).where(
        BudgetLimit.user_id == current_user.id,
        BudgetLimit.category_id == category_id,
        BudgetLimit.month == normalized_month,
    )
    result = await session.execute(statement)
    limit = result.scalar_one_or_none()

    if limit is None:
        raise NotFound("Бюджетный лимит не найден")

    limit.limit_amount_cents = limit_amount_cents
    await session.flush()

    return limit


@router.get(
    "/status",
    response_model=list[LimitStatusDTO],
    summary="Получить состояние бюджетных лимитов",
    description=(
        "Возвращает фактические расходы, остаток и прогноз для каждого "
        "бюджетного лимита текущего пользователя. Если лимитов нет, "
        "возвращается пустой список."
    ),
    responses=error_responses(401),
)
async def get_statuses(
    current_user: CurrentUser,
    session: SessionDep,
    clock: ClockDep,
) -> list[LimitStatusDTO]:
    statement = select(BudgetLimit).where(
        BudgetLimit.user_id == current_user.id,
    )
    result = await session.execute(statement)
    limits = result.scalars().all()

    today = clock.today()
    result_data: list[LimitStatusDTO] = []

    for limit_obj in limits:
        month_start = normalize_month(limit_obj.month)
        month_after = next_month(month_start)

        # Факт и текущий темп не учитывают будущие операции.
        if today < month_start:
            actual_period_end = month_start
        elif today < month_after:
            actual_period_end = today + timedelta(days=1)
        else:
            actual_period_end = month_after

        spent_statement = select(
            func.coalesce(
                func.sum(Operation.amount_cents),
                0,
            )
        ).where(
            Operation.user_id == current_user.id,
            Operation.category_id == limit_obj.category_id,
            Operation.kind == "expense",
            Operation.occurred_at >= day_start(month_start),
            Operation.occurred_at < day_start(actual_period_end),
        )
        spent_amount_cents = int(await session.scalar(spent_statement) or 0)

        limit_dec = Decimal(limit_obj.limit_amount_cents) / Decimal("100")
        spent_dec = Decimal(spent_amount_cents) / Decimal("100")

        if today < month_start:
            # Будущий месяц: факт и прогноз пока нулевые.
            projected_dec = Decimal("0.00")
        elif today >= month_after:
            # Прошлый месяц завершён: прогноз равен факту.
            projected_dec = spent_dec
        else:
            # Прогноз вычисляется только для текущего месяца.
            forecast_data = forecast_month(
                spent_to_date=spent_dec,
                year=month_start.year,
                month=month_start.month,
                as_of=today,
            )
            projected_value = forecast_data["projected_total"]

            if not isinstance(
                projected_value,
                Decimal,
            ):
                raise TypeError("Прогноз должен возвращать Decimal")

            projected_dec = projected_value

        projected_amount_cents = int(
            (projected_dec * Decimal("100")).quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP,
            )
        )

        status_value = limit_status(
            limit_dec,
            spent_dec,
            projected_dec,
        )
        percent = (
            (spent_dec / limit_dec).quantize(
                Decimal("0.0001"),
                rounding=ROUND_HALF_UP,
            )
            if limit_dec > 0
            else Decimal("0.0000")
        )

        # Процент хранится с точностью до четырёх знаков после запятой.
        result_data.append(
            LimitStatusDTO.model_validate(
                {
                    "category_id": limit_obj.category_id,
                    "month": month_start,
                    "limit_amount_cents": limit_obj.limit_amount_cents,
                    "spent_amount_cents": spent_amount_cents,
                    "remaining_amount_cents": max(
                        limit_obj.limit_amount_cents - spent_amount_cents,
                        0,
                    ),
                    "projected_amount_cents": projected_amount_cents,
                    "percent": percent,
                    "status": status_value.name,
                }
            )
        )

    return result_data
