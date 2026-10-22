
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.domains.budget.models import BudgetLimit
from app.domains.budget.service import limit_status
from app.domains.ledger.models import Category
from app.interface.api.deps import CurrentUser, SessionDep

router = APIRouter(prefix='/api/v1/budget_limits', tags=['budget-limits'])

class LimitCreate(BaseModel):
    category_id: UUID
    month: date
    limit_amount_cents: int = Field(gt=0)

class LimitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    category_id: UUID
    month: date
    limit_amount_cents: int

@router.post('', status_code=201, response_model=LimitRead)
async def create_limit(payload: LimitCreate, current_user: CurrentUser, session: SessionDep):
    if payload.limit_amount_cents <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail='Лимит должен быть больше 0')

    category_stmt = select(Category).where(
        Category.id == payload.category_id,
        Category.user_id == current_user.id,
    )

    category_result =  await session.execute(category_stmt)
    category = category_result.scalar_one_or_none()

    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Категория не найдена",)

    stmt = select(BudgetLimit).where(
        BudgetLimit.user_id == current_user.id,
        BudgetLimit.category_id == payload.category_id,
        BudgetLimit.month == payload.month,)

    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail='Лимит уже существует')

    new_limit = BudgetLimit(user_id=current_user.id, **payload.model_dump())
    session.add(new_limit)
    await session.flush()

    return new_limit

@router.get("", response_model=list[LimitRead])
async def limits_list(current_user: CurrentUser, session: SessionDep):

    stmt = select(BudgetLimit).where(BudgetLimit.user_id == current_user.id)
    result = await session.execute(stmt)
    return result.scalars().all()

@router.put('/{category_id}', response_model=LimitRead)
async def update_limit(category_id: UUID, month: date,
                       limit_amount_cents: int, current_user: CurrentUser, session: SessionDep):

    if limit_amount_cents <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail='Лимит должен быть больше 0')

    stmt = select(BudgetLimit).where(
        BudgetLimit.user_id == current_user.id,
        BudgetLimit.category_id == category_id,
        BudgetLimit.month == month,
    )
    result = await session.execute(stmt)
    limit = result.scalar_one_or_none()

    if limit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Лимит не найден')

    limit.limit_amount_cents = limit_amount_cents
    await session.flush()
    return limit

@router.get('/status')
async def get_statuses(current_user: CurrentUser, session: SessionDep):

    stmt = select(BudgetLimit).where(BudgetLimit.user_id == current_user.id)
    result = await session.execute(stmt)
    limits = result.scalars().all()

    result_data = []
    for limit_obj in limits:
        limit_dec = Decimal(limit_obj.limit_amount_cents) / Decimal('100')
        spent_dec = Decimal('0')
        projected_dec = Decimal('0')

        status_val = limit_status(limit_dec, spent_dec, projected_dec)
        percent = (
            (spent_dec / limit_dec).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
            if limit_dec > 0 else Decimal('0')
        )

        result_data.append({
            'category_id': limit_obj.category_id,
            'month': limit_obj.month,
            'limit_amount_cents': limit_obj.limit_amount_cents,
            'spent_amount_cents': 0,
            'remaining_amount_cents': limit_obj.limit_amount_cents,
            'projected_amount_cents': 0,
            'percent': percent,
            'status': status_val.name
        })
    return result_data