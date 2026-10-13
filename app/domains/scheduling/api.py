"""API повторяющихся операций: CRUD правил, пауза/актив, генерация (docs/03 §S4.2)."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, status
from pydantic import BaseModel

from app.domains.scheduling.models import RecurringRule
from app.domains.scheduling.schemas import (
    RecurringExecutionDTO,
    RecurringRuleCreate,
    RecurringRuleDTO,
    RecurringRuleUpdate,
)
from app.domains.scheduling.service import RecurringService
from app.interface.api.deps import CurrentUser, SessionDep

router = APIRouter(prefix="/api/v1/recurring/rules", tags=["recurring"])


@router.post("", response_model=RecurringRuleDTO, status_code=status.HTTP_201_CREATED)
async def create_rule(
    payload: RecurringRuleCreate,
    _current_user: CurrentUser,
    session: SessionDep,
) -> RecurringRule:
    rule = RecurringRule(
        user_id=_current_user.id,
        category_id=payload.category_id,
        kind=payload.kind,
        interval=payload.interval,
        amount_cents=payload.amount_cents,
        note=payload.note,
        start_date=payload.start_date,
        end_date=payload.end_date,
        next_run_at=payload.start_date,
    )
    service = RecurringService(session)
    return await service.create_rule(rule)


@router.get("", response_model=list[RecurringRuleDTO])
async def list_rules(
    _current_user: CurrentUser,
    session: SessionDep,
) -> list[RecurringRule]:
    service = RecurringService(session)
    return await service.list_rules()


@router.get("/{rule_id}", response_model=RecurringRuleDTO)
async def get_rule(
    rule_id: UUID,
    _current_user: CurrentUser,
    session: SessionDep,
) -> RecurringRule:
    service = RecurringService(session)
    rule = await service.get_rule(str(rule_id))
    if rule is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Правило не найдено")
    return rule


@router.patch("/{rule_id}", response_model=RecurringRuleDTO)
async def update_rule(
    rule_id: UUID,
    payload: RecurringRuleUpdate,
    _current_user: CurrentUser,
    session: SessionDep,
) -> RecurringRule:
    service = RecurringService(session)
    rule = await service.update_rule(
        str(rule_id),
        category_id=payload.category_id,
        kind=payload.kind,
        interval=payload.interval,
        amount_cents=payload.amount_cents,
        note=payload.note,
        start_date=payload.start_date,
        end_date=payload.end_date,
        is_active=payload.is_active,
    )
    if rule is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Правило не найдено")
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: UUID,
    _current_user: CurrentUser,
    session: SessionDep,
) -> None:
    service = RecurringService(session)
    ok = await service.delete_rule(str(rule_id))
    if not ok:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Правило не найдено")


class RunRulesRequest(BaseModel):
    until: datetime | None = None
    dry_run: bool = False


@router.post("/run", response_model=list[RecurringExecutionDTO])
async def run_rules(
    payload: RunRulesRequest,
    _current_user: CurrentUser,
    session: SessionDep,
) -> list[RecurringExecutionDTO]:
    service = RecurringService(session)
    executions = await service.generate_due_operations(
        until=payload.until,
        dry_run=payload.dry_run,
    )
    return [RecurringExecutionDTO.model_validate(e) for e in executions]