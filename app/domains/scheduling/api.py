"""API повторяющихся операций."""

from datetime import UTC, datetime, time
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, status

from app.domains.scheduling.models import RecurringRule
from app.domains.scheduling.schemas import (
    RecurringExecutionDTO,
    RecurringRuleCreate,
    RecurringRuleDTO,
    RecurringRuleUpdate,
    RunRulesRequest,
)
from app.domains.scheduling.service import RecurringService
from app.interface.api.deps import CurrentUser, SessionDep
from app.interface.api.schemas import error_responses

router = APIRouter(
    prefix="/api/v1/recurring/rules",
    tags=["Повторяющиеся операции"],
)

RuleId = Annotated[
    UUID,
    Path(
        description="Идентификатор повторяющегося правила.",
    ),
]


@router.post(
    "",
    response_model=RecurringRuleDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Создать повторяющееся правило",
    description=(
        "Создаёт правило автоматического формирования расходных операций "
        "с ежедневной, еженедельной или ежемесячной периодичностью."
    ),
    responses=error_responses(401, 422),
)
async def create_rule(
    payload: RecurringRuleCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> RecurringRule:
    rule = RecurringRule(
        user_id=current_user.id,
        category_id=payload.category_id,
        kind=payload.kind,
        interval=payload.interval,
        amount_cents=payload.amount_cents,
        note=payload.note,
        start_date=payload.start_date,
        end_date=payload.end_date,
        next_run_at=datetime(
            payload.start_date.year,
            payload.start_date.month,
            payload.start_date.day,
            12,
            0,
            0,
            tzinfo=UTC,
        ),
    )

    service = RecurringService(session)
    return await service.create_rule(rule)


@router.get(
    "",
    response_model=list[RecurringRuleDTO],
    summary="Получить повторяющиеся правила",
    description=(
        "Возвращает повторяющиеся правила текущего пользователя. "
        "Если правил нет, возвращается пустой список."
    ),
    responses=error_responses(401),
)
async def list_rules(
    current_user: CurrentUser,
    session: SessionDep,
) -> list[RecurringRule]:
    service = RecurringService(session)
    return await service.list_rules(
        str(current_user.id),
    )


@router.get(
    "/{rule_id}",
    response_model=RecurringRuleDTO,
    summary="Получить повторяющееся правило",
    description=(
        "Возвращает правило текущего пользователя по идентификатору. "
        "Чужое и несуществующее правило возвращают одинаковую ошибку 404."
    ),
    responses=error_responses(401, 404, 422),
)
async def get_rule(
    rule_id: RuleId,
    current_user: CurrentUser,
    session: SessionDep,
) -> RecurringRule:
    service = RecurringService(session)
    return await service.get_rule(
        str(rule_id),
        str(current_user.id),
    )


@router.patch(
    "/{rule_id}",
    response_model=RecurringRuleDTO,
    summary="Изменить повторяющееся правило",
    description=(
        "Частично изменяет переданные поля повторяющегося правила. "
        "Поля note и end_date можно очистить значением null."
    ),
    responses=error_responses(401, 404, 422),
)
async def update_rule(
    rule_id: RuleId,
    payload: RecurringRuleUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> RecurringRule:
    service = RecurringService(session)

    # Меняем только переданные поля. Значение null допустимо
    # для note и end_date и обрабатывается сервисом.
    fields = payload.model_dump(
        exclude_unset=True,
    )

    return await service.update_rule(
        str(rule_id),
        str(current_user.id),
        **fields,
    )


@router.delete(
    "/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Отключить повторяющееся правило",
    description=(
        "Выполняет мягкое удаление правила: оно становится неактивным "
        "и больше не участвует в автоматической генерации операций."
    ),
    responses=error_responses(401, 404, 422),
)
async def delete_rule(
    rule_id: RuleId,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    service = RecurringService(session)
    await service.delete_rule(
        str(rule_id),
        str(current_user.id),
    )


@router.post(
    "/run",
    response_model=list[RecurringExecutionDTO],
    summary="Запустить генерацию повторяющихся операций",
    description=(
        "Запускает правила текущего пользователя вручную. "
        "При dry_run=true только показывает будущие выполнения. "
        "При обычном запуске выполняет полный catch-up и не создаёт дубли."
    ),
    responses=error_responses(401, 422),
)
async def run_rules(
    payload: RunRulesRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> list[RecurringExecutionDTO]:
    date_from = (
        datetime.combine(
            payload.date_from,
            time.min,
            tzinfo=UTC,
        )
        if payload.date_from is not None
        else None
    )
    date_to = (
        datetime.combine(
            payload.date_to,
            time.max,
            tzinfo=UTC,
        )
        if payload.date_to is not None
        else None
    )

    service = RecurringService(session)
    executions = await service.generate_due_operations(
        user_id=current_user.id,
        until=date_to,
        date_from=date_from,
        dry_run=payload.dry_run,
    )

    return [
        RecurringExecutionDTO.model_validate(
            execution,
        )
        for execution in executions
    ]
