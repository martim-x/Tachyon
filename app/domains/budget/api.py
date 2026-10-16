
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import date
from uuid import UUID
from pydantic import BaseModel
from decimal import Decimal, ROUND_HALF_UP


from app.core.persistence.session import get_session, engine
from app.core.persistence.base import Base
from app.domains.budget.models import BudgetLimit
from app.domains.budget.service import limit_status

router = APIRouter(prefix='/api/v1/budget_limits', tags=['budget-limits'])

class LimitCreate(BaseModel):
    user_id: UUID
    category_id: UUID
    month: date
    limit_amount_cents: int

@router.post('', status_code=201)
def create_limit(payload: LimitCreate, db: Session = Depends(get_session)):
    if payload.limit_amount_cents <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail='Лимит должен быть больше 0')

    existing = db.query(BudgetLimit).filter(
        BudgetLimit.user_id == payload.user_id,
        BudgetLimit.category_id == payload.category_id,
        BudgetLimit.month == payload.month,
    ).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Лимит уже существует')

    new_limit = BudgetLimit(**payload.model_dump())
    db.add(new_limit)
    db.commit()
    db.refresh(new_limit)
    return new_limit

@router.get('', response_model=list[BudgetLimit])
def limits_list(user_id: UUID, db: Session = Depends(get_session)):
    return db.query(BudgetLimit).filter(BudgetLimit.user_id == user_id).all()

@router.put('/{category_id}')
def update_limit(category_id: UUID, user_id: UUID, month: date, limit_amount_cents: int, db: Session = Depends(get_session)):
    if limit_amount_cents <= 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail='Лимит должен быть больше 0')

    limit = db.query(BudgetLimit).filter(
        BudgetLimit.user_id == user_id,
        BudgetLimit.category_id == category_id,
        BudgetLimit.month == month,
    ).first()
    if not limit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Не найдено')

    limit.limit_amount_cents = limit_amount_cents
    db.commit()
    db.refresh(limit)
    return limit

@router.get('/status')
def get_statuses(user_id: UUID, db: Session = Depends(get_session)):
    limits = db.query(BudgetLimit).filter(BudgetLimit.user_id == user_id).all()
    result = []
    for l in limits:
        limit_dec = Decimal(l.limit_amount_cents) / Decimal('100')
        spent_dec = Decimal('0')
        projected_dec = Decimal('0')

        status_val = limit_status(limit_dec, spent_dec, projected_dec)
        percent = (
            (spent_dec / limit_dec).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
            if limit_dec > 0 else Decimal('0')
        )

        result.append({
            'limit_amount_cents': l.limit_amount_cents,
            'spent_amount_cents': 0,
            'remaining_amount_cents': l.limit_amount_cents,
            'projected_amount_cents': 0,
            'percent': percent,
            'status': status_val.name
        })
    return result