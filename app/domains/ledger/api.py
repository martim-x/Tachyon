"""HTTP API операций и категорий."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Path, Query, status

from app.domains.ledger.models import Category, Operation
from app.domains.ledger.repository import OperationRepository
from app.domains.ledger.schemas import (
    CategoryCreate,
    CategoryDTO,
    CategoryUpdate,
    Kind,
    OperationCreate,
    OperationDTO,
    OperationListQuery,
    OperationPageDTO,
    OperationUpdate,
)
from app.domains.ledger.service import (
    CategoryService,
    OperationService,
)
from app.infrastructure.event_handlers import evaluate_budget_notifications
from app.interface.api.deps import ClockDep, CurrentUser, SessionDep
from app.interface.api.schemas import error_responses

router = APIRouter(
    prefix="/api/v1",
    tags=["Операции"],
)

OperationId = Annotated[
    UUID,
    Path(description="Идентификатор операции"),
]

CategoryId = Annotated[
    UUID,
    Path(description="Идентификатор категории"),
]


def _operation_dto(
    operation: Operation,
) -> OperationDTO:
    return OperationDTO(
        id=operation.id,
        user_id=operation.user_id,
        category_id=operation.category_id,
        amount=OperationRepository.to_money(operation).amount,
        kind=cast(Kind, operation.kind),
        occurred_at=operation.occurred_at,
        note=operation.note,
        source=operation.source,
    )


def _category_dto(
    category: Category,
) -> CategoryDTO:
    return CategoryDTO(
        id=category.id,
        user_id=category.user_id,
        name=category.name,
        kind=category.kind,
        color=category.color,
        is_default=category.is_default,
    )


@router.post(
    "/operations",
    response_model=OperationDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Создать операцию",
    description=(
        "Создаёт доход или расход текущего пользователя. "
        "Сумма передаётся как Decimal с двумя знаками."
    ),
    responses=error_responses(401, 404, 422),
)
async def create_operation(
    payload: OperationCreate,
    current_user: CurrentUser,
    session: SessionDep,
    clock: ClockDep,
) -> OperationDTO:
    operation = await OperationService(session).create(payload)

    await evaluate_budget_notifications(
        session=session,
        user_id=current_user.id,
        month=operation.occurred_at.date(),
        clock=clock,
    )

    return _operation_dto(operation)


@router.get(
    "/operations",
    response_model=OperationPageDTO,
    summary="Получить список операций",
    description=(
        "Возвращает страницу операций текущего пользователя с фильтрами по датам, категории и типу."
    ),
    responses=error_responses(401, 422),
)
async def list_operations(
    query: Annotated[
        OperationListQuery,
        Query(),
    ],
    _current_user: CurrentUser,
    session: SessionDep,
) -> OperationPageDTO:
    operations, total = await OperationService(session).list_page(query)

    return OperationPageDTO(
        items=[_operation_dto(operation) for operation in operations],
        total=total,
        page=query.page,
        limit=query.limit,
    )


@router.get(
    "/operations/{operation_id}",
    response_model=OperationDTO,
    summary="Получить операцию",
    description=(
        "Возвращает операцию текущего пользователя. "
        "Чужая и отсутствующая операция дают одинаковый 404."
    ),
    responses=error_responses(401, 404, 422),
)
async def get_operation(
    operation_id: OperationId,
    _current_user: CurrentUser,
    session: SessionDep,
) -> OperationDTO:
    operation = await OperationService(session).get(operation_id)

    return _operation_dto(operation)


@router.patch(
    "/operations/{operation_id}",
    response_model=OperationDTO,
    summary="Изменить операцию",
    description=("Частично изменяет операцию текущего пользователя."),
    responses=error_responses(401, 404, 422),
)
async def patch_operation(
    operation_id: OperationId,
    payload: OperationUpdate,
    current_user: CurrentUser,
    session: SessionDep,
    clock: ClockDep,
) -> OperationDTO:
    operation = await OperationService(session).update(
        operation_id,
        payload,
    )

    await evaluate_budget_notifications(
        session=session,
        user_id=current_user.id,
        month=operation.occurred_at.date(),
        clock=clock,
    )

    return _operation_dto(operation)


@router.delete(
    "/operations/{operation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить операцию",
    description=("Удаляет операцию текущего пользователя."),
    responses=error_responses(401, 404, 422),
)
async def delete_operation(
    operation_id: OperationId,
    _current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await OperationService(session).delete(operation_id)


@router.get(
    "/categories",
    response_model=list[CategoryDTO],
    tags=["Категории"],
    summary="Получить категории",
    description=("Возвращает категории доходов и расходов текущего пользователя."),
    responses=error_responses(401),
)
async def list_categories(
    _current_user: CurrentUser,
    session: SessionDep,
) -> list[CategoryDTO]:
    categories = await CategoryService(session).list()

    return [_category_dto(category) for category in categories]


@router.post(
    "/categories",
    response_model=CategoryDTO,
    status_code=status.HTTP_201_CREATED,
    tags=["Категории"],
    summary="Создать категорию",
    description=(
        "Создаёт категорию доходов или расходов. Название уникально для текущего пользователя."
    ),
    responses=error_responses(401, 409, 422),
)
async def create_category(
    payload: CategoryCreate,
    _current_user: CurrentUser,
    session: SessionDep,
) -> CategoryDTO:
    category = await CategoryService(session).create(payload)

    return _category_dto(category)


@router.get(
    "/categories/{category_id}",
    response_model=CategoryDTO,
    tags=["Категории"],
    summary="Получить категорию",
    description=("Возвращает категорию текущего пользователя."),
    responses=error_responses(401, 404, 422),
)
async def get_category(
    category_id: CategoryId,
    _current_user: CurrentUser,
    session: SessionDep,
) -> CategoryDTO:
    category = await CategoryService(session).get(category_id)

    return _category_dto(category)


@router.patch(
    "/categories/{category_id}",
    response_model=CategoryDTO,
    tags=["Категории"],
    summary="Изменить категорию",
    description=("Изменяет название или тип категории."),
    responses=error_responses(
        401,
        404,
        409,
        422,
    ),
)
async def patch_category(
    category_id: CategoryId,
    payload: CategoryUpdate,
    _current_user: CurrentUser,
    session: SessionDep,
) -> CategoryDTO:
    category = await CategoryService(session).update(
        category_id,
        payload,
    )

    return _category_dto(category)


@router.delete(
    "/categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Категории"],
    summary="Удалить категорию",
    description=("Удаляет категорию текущего пользователя."),
    responses=error_responses(401, 404, 422),
)
async def delete_category(
    category_id: CategoryId,
    _current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await CategoryService(session).delete(category_id)
