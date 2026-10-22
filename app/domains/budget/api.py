from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.domains.budget.models import BudgetLimit
from app.domains.budget.service import limit_status
from app.domains.forecasting.service import forecast_month
from app.domains.ledger.models import Category, Operation
from app.interface.api.deps import (
    ClockDep,
    CurrentUser,
    SessionDep,
)

router = APIRouter(
    prefix="/api/v1/budget_limits",
    tags=["budget-limits"],
)


def normalize_month(value: date) -> date:
    """Привести любую дату к первому дню её месяца."""

    return value.replace(day=1)


def next_month(month: date) -> date:
    """Первый день следующего месяца."""

    if month.month == 12:
        return date(month.year + 1, 1, 1)

    return date(
        month.year,
        month.month + 1,
        1,
    )


def day_start(day: date) -> datetime:
    """Начало календарного дня в UTC."""

    return datetime(
        day.year,
        day.month,
        day.day,
        tzinfo=UTC,
    )


class LimitCreate(BaseModel):
    category_id: UUID
    month: date
    limit_amount_cents: int = Field(gt=0)

    @field_validator("month")
    @classmethod
    def month_starts_on_first_day(
        cls,
        value: date,
    ) -> date:
        return normalize_month(value)


class LimitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    category_id: UUID
    month: date
    limit_amount_cents: int


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=LimitRead,
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Категория не найдена",
        )

    stmt = select(BudgetLimit).where(
        BudgetLimit.user_id == current_user.id,
        BudgetLimit.category_id == payload.category_id,
        BudgetLimit.month == payload.month,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Лимит уже существует",
        )

    new_limit = BudgetLimit(
        user_id=current_user.id,
        **payload.model_dump(),
    )
    session.add(new_limit)

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Лимит уже существует",
        ) from exc

    return new_limit


@router.get(
    "",
    response_model=list[LimitRead],
)
async def limits_list(
    current_user: CurrentUser,
    session: SessionDep,
):
    stmt = select(BudgetLimit).where(
        BudgetLimit.user_id == current_user.id,
    )
    result = await session.execute(stmt)

    return result.scalars().all()


@router.put(
    "/{category_id}",
    response_model=LimitRead,
)
async def update_limit(
    category_id: UUID,
    month: date,
    limit_amount_cents: int,
    current_user: CurrentUser,
    session: SessionDep,
):
    month = normalize_month(month)

    if limit_amount_cents <= 0:
        raise HTTPException(
            status_code=(status.HTTP_422_UNPROCESSABLE_CONTENT),
            detail="Лимит должен быть больше 0",
        )

    stmt = select(BudgetLimit).where(
        BudgetLimit.user_id == current_user.id,
        BudgetLimit.category_id == category_id,
        BudgetLimit.month == month,
    )
    result = await session.execute(stmt)
    limit = result.scalar_one_or_none()

    if limit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Лимит не найден",
        )

    limit.limit_amount_cents = limit_amount_cents
    await session.flush()

    return limit


@router.get("/status")
async def get_statuses(
    current_user: CurrentUser,
    session: SessionDep,
    clock: ClockDep,
):
    stmt = select(BudgetLimit).where(
        BudgetLimit.user_id == current_user.id,
    )
    result = await session.execute(stmt)
    limits = result.scalars().all()

    today = clock.today()
    result_data = []

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

        spent_stmt = select(
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
        spent_amount_cents = int(await session.scalar(spent_stmt) or 0)

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

        status_val = limit_status(
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
            else Decimal("0")
        )

        result_data.append(
            {
                "category_id": limit_obj.category_id,
                "month": month_start,
                "limit_amount_cents": (limit_obj.limit_amount_cents),
                "spent_amount_cents": (spent_amount_cents),
                "remaining_amount_cents": max(
                    limit_obj.limit_amount_cents - spent_amount_cents,
                    0,
                ),
                "projected_amount_cents": (projected_amount_cents),
                "percent": percent,
                "status": status_val.name,
            }
        )

    return result_data
