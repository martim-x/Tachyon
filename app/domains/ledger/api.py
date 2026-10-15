"""HTTP-интерфейс операций: разбор запроса, вызов сервиса, сериализация (docs/02)."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.domains.ledger.models import Category, Operation
from app.domains.ledger.repository import OperationRepository
from app.domains.ledger.schemas import (
    CategoryCreate,
    CategoryDTO,
    Kind,
    OperationCreate,
    OperationDTO,
    OperationListQuery,
    OperationPageDTO,
    OperationUpdate,
)
from app.domains.ledger.service import CategoryService, OperationService
from app.interface.api.deps import CurrentUser, SessionDep

router = APIRouter(prefix="/api/v1", tags=["Операции"])


def _operation_dto(operation: Operation) -> OperationDTO:
    """Сумма читается только через репозиторий (docs/02, правило границы денег)."""
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


def _category_dto(category: Category) -> CategoryDTO:
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
)
async def create_operation(
    payload: OperationCreate,
    _current_user: CurrentUser,
    session: SessionDep,
) -> OperationDTO:
    operation = await OperationService(session).create(payload)
    return _operation_dto(operation)


@router.get("/operations", response_model=OperationPageDTO)
async def list_operations(
    query: Annotated[OperationListQuery, Query()],
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


@router.get("/operations/{operation_id}", response_model=OperationDTO)
async def get_operation(
    operation_id: UUID,
    _current_user: CurrentUser,
    session: SessionDep,
) -> OperationDTO:
    operation = await OperationService(session).get(operation_id)
    return _operation_dto(operation)


@router.patch("/operations/{operation_id}", response_model=OperationDTO)
async def patch_operation(
    operation_id: UUID,
    payload: OperationUpdate,
    _current_user: CurrentUser,
    session: SessionDep,
) -> OperationDTO:
    operation = await OperationService(session).update(operation_id, payload)
    return _operation_dto(operation)


@router.delete("/operations/{operation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_operation(
    operation_id: UUID,
    _current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await OperationService(session).delete(operation_id)


@router.get("/categories", response_model=list[CategoryDTO], tags=["Категории"])
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
)
async def create_category(
    payload: CategoryCreate,
    _current_user: CurrentUser,
    session: SessionDep,
) -> CategoryDTO:
    category = await CategoryService(session).create(payload)
    return _category_dto(category)
