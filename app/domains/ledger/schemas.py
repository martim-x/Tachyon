"""Схемы операций и категорий (docs/02: OperationCreate, OperationDTO, CategoryDTO).

amount ограничен 9 999 999.99: в БД копейки хранятся в 32-битном Integer
(максимум 2 147 483 647), диапазон схемы выровнен под колонку, чтобы валидное
по API значение не падало на вставке с 500 (docs/02 §«Правила денег»).
occurred_at принимает только метки с таймзоной; не-UTC смещения сервис
нормализует в UTC перед записью.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator

MAX_NOTE_LENGTH = 500
MAX_AMOUNT = Field(max_digits=9, decimal_places=2, gt=0)

Kind = Literal["income", "expense"]


def _strip_name(value: object) -> object:
    """Пробелы по краям не считаются частью имени: строка из пробелов — пустая."""
    if isinstance(value, str):
        return value.strip()
    return value


class OperationCreate(BaseModel):
    """Тело POST /operations: user_id и source клиенту не принадлежат."""

    category_id: UUID
    amount: Decimal = MAX_AMOUNT
    kind: Kind
    occurred_at: AwareDatetime | None = None
    note: str | None = Field(default=None, max_length=MAX_NOTE_LENGTH)


class OperationUpdate(BaseModel):
    """Тело PATCH /operations/{id}: меняются только переданные поля."""

    category_id: UUID | None = None
    amount: Decimal | None = Field(default=None, max_digits=9, decimal_places=2, gt=0)
    kind: Kind | None = None
    occurred_at: AwareDatetime | None = None
    note: str | None = Field(default=None, max_length=MAX_NOTE_LENGTH)

    @model_validator(mode="after")
    def _not_null_columns_stay_not_null(self) -> "OperationUpdate":
        forbidden = {
            name
            for name in ("category_id", "amount", "kind", "occurred_at")
            if name in self.model_fields_set and getattr(self, name) is None
        }
        if forbidden:
            raise ValueError(f"нельзя обнулить: {', '.join(sorted(forbidden))}")
        return self


class OperationDTO(BaseModel):
    """Ответ по операции: сумма Decimal с двумя знаками, без дробной потери точности."""

    id: UUID
    user_id: UUID
    category_id: UUID
    amount: Decimal
    kind: Kind
    occurred_at: datetime
    note: str | None
    source: str


class CategoryDTO(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    kind: str
    color: str | None
    is_default: bool


class CategoryCreate(BaseModel):
    """Тело POST /categories: только name и kind; остальное — дефолты.

    max_length согласован с колонкой categories.name (String(50)):
    более длинное имя не должно доходить до БД и падать с 500.
    user_id клиент не задаёт: его ставит ScopedRepository из UserContext.
    """

    name: str = Field(min_length=1, max_length=50)
    kind: Kind

    @field_validator("name", mode="before")
    @classmethod
    def _normalize_name(cls, value: object) -> object:
        return _strip_name(value)


class CategoryUpdate(BaseModel):
    """Тело PATCH /categories/{id}: меняются только переданные поля."""

    name: str | None = Field(default=None, min_length=1, max_length=50)
    kind: Kind | None = None

    @field_validator("name", mode="before")
    @classmethod
    def _normalize_name(cls, value: object) -> object:
        return _strip_name(value)

    @model_validator(mode="after")
    def _not_null_columns_stay_not_null(self) -> "CategoryUpdate":
        forbidden = {
            name
            for name in ("name", "kind")
            if name in self.model_fields_set and getattr(self, name) is None
        }
        if forbidden:
            raise ValueError(f"нельзя обнулить: {', '.join(sorted(forbidden))}")
        return self


class OperationPageDTO(BaseModel):
    """Страница списка и метаданные общего количества (docs/03 §S3.2)."""

    items: list[OperationDTO]
    total: int
    page: int
    limit: int


class OperationListQuery(BaseModel):
    """Параметры GET /operations: фильтры и пагинация одним query-моделью.

    from и to - календарные дни (UTC), включительно с обеих сторон.
    """

    model_config = {"populate_by_name": True}

    date_from: date | None = Field(default=None, alias="from")
    date_to: date | None = Field(default=None, alias="to")
    category_id: UUID | None = None
    kind: Kind | None = Field(default=None, alias="type")
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def _period_is_ordered(self) -> "OperationListQuery":
        if self.date_from is not None and self.date_to is not None:
            if self.date_from > self.date_to:
                raise ValueError("from не может быть позже to")
        return self
