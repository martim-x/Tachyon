
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.persistence.session import get_session
from app.domains.budget.models import BudgetLimit
from app.domains.budget.service import limit_status

router = APIRouter(prefix='/api/v1/budget_limits', tags=['budget-limits'])

class LimitCreate(BaseModel):
    user_id: UUID
    category_id: UUID
    month: date
    limit_amount_cents: int

@router.post('', status_code=201, dependencies= [Depends(get_session)])
async def create_limit(payload: LimitCreate, request: Request):
    db: AsyncSession = request.state.db
    if payload.limit_amount_cents <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail='Лимит должен быть больше 0')

    stmt = select(BudgetLimit).where(
        BudgetLimit.user_id == payload.user_id,
        BudgetLimit.category_id == payload.category_id,
        BudgetLimit.month == payload.month,
    )
    result = await db.execute(stmt)
    existing = result.scalars().first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail='Лимит уже существует')

    new_limit = BudgetLimit(**payload.model_dump())
    db.add(new_limit)

    return new_limit

@router.get('', response_model=list[BudgetLimit], dependencies= [Depends(get_session)])
async def limits_list(user_id: UUID, request: Request):
    db: AsyncSession = request.state.db

    stmt = select(BudgetLimit).where(BudgetLimit.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalars().all()

@router.put('/{category_id}', dependencies= [Depends(get_session)])
async def update_limit(category_id: UUID, user_id: UUID, month: date,
                       limit_amount_cents: int, request: Request):
    db: AsyncSession = request.state.db

    if limit_amount_cents <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail='Лимит должен быть больше 0')

    stmt = select(BudgetLimit).where(
        BudgetLimit.user_id == user_id,
        BudgetLimit.category_id == category_id,
        BudgetLimit.month == month,
    )
    result = await db.execute(stmt)
    limit = result.scalars().first()

    if not limit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Не найдено')

    limit.limit_amount_cents = limit_amount_cents
    await db.refresh(limit)
    return limit

@router.get('/status', dependencies= [Depends(get_session)])
async def get_statuses(user_id: UUID, request: Request):
    db: AsyncSession = request.state.db

    stmt = select(BudgetLimit).where(BudgetLimit.user_id == user_id)
    result = await db.execute(stmt)
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
            'limit_amount_cents': limit_obj.limit_amount_cents,
            'spent_amount_cents': 0,
            'remaining_amount_cents': limit_obj.limit_amount_cents,
            'projected_amount_cents': 0,
            'percent': percent,
            'status': status_val.name
        })
    return result_data