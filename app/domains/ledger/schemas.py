"""Схемы операций и категорий."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

MAX_NOTE_LENGTH = 500

Kind = Literal["income", "expense"]


def _strip_name(value: object) -> object:
    """Убрать пробелы по краям названия."""

    if isinstance(value, str):
        return value.strip()

    return value


class OperationCreate(BaseModel):
    category_id: UUID = Field(
        description="Категория операции",
    )
    amount: Decimal = Field(
        gt=0,
        max_digits=9,
        decimal_places=2,
        description="Сумма операции с двумя знаками",
    )
    kind: Kind = Field(
        description="Тип операции: income или expense",
    )
    occurred_at: AwareDatetime | None = Field(
        default=None,
        description=(
            "Дата и время операции с часовым поясом; по умолчанию используется текущее время"
        ),
    )
    note: str | None = Field(
        default=None,
        max_length=MAX_NOTE_LENGTH,
        description="Комментарий к операции",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "category_id": ("20000000-0000-0000-0000-000000000001"),
                "amount": "1250.50",
                "kind": "expense",
                "occurred_at": ("2026-10-15T12:00:00+00:00"),
                "note": "Покупка продуктов",
            }
        }
    )


class OperationUpdate(BaseModel):
    category_id: UUID | None = Field(
        default=None,
        description="Новая категория операции",
    )
    amount: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=9,
        decimal_places=2,
        description="Новая сумма операции",
    )
    kind: Kind | None = Field(
        default=None,
        description="Новый тип операции",
    )
    occurred_at: AwareDatetime | None = Field(
        default=None,
        description="Новая дата и время операции",
    )
    note: str | None = Field(
        default=None,
        max_length=MAX_NOTE_LENGTH,
        description="Новый комментарий",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "amount": "1400.00",
                "note": "Уточнённая сумма",
            }
        }
    )

    @model_validator(mode="after")
    def _not_null_columns_stay_not_null(
        self,
    ) -> "OperationUpdate":
        forbidden = {
            name
            for name in (
                "category_id",
                "amount",
                "kind",
                "occurred_at",
            )
            if (name in self.model_fields_set and getattr(self, name) is None)
        }

        if forbidden:
            raise ValueError(f"нельзя обнулить: {', '.join(sorted(forbidden))}")

        return self


class OperationDTO(BaseModel):
    id: UUID
    user_id: UUID
    category_id: UUID
    amount: Decimal = Field(
        decimal_places=2,
        description="Сумма операции",
    )
    kind: Kind
    occurred_at: datetime
    note: str | None
    source: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": ("30000000-0000-0000-0000-000000000001"),
                "user_id": ("10000000-0000-0000-0000-000000000001"),
                "category_id": ("20000000-0000-0000-0000-000000000001"),
                "amount": "1250.50",
                "kind": "expense",
                "occurred_at": ("2026-10-15T12:00:00+00:00"),
                "note": "Покупка продуктов",
                "source": "manual",
            }
        }
    )


class CategoryDTO(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    kind: str
    color: str | None
    is_default: bool

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": ("20000000-0000-0000-0000-000000000001"),
                "user_id": ("10000000-0000-0000-0000-000000000001"),
                "name": "Продукты",
                "kind": "expense",
                "color": "#22AA66",
                "is_default": False,
            }
        }
    )


class CategoryCreate(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=50,
        description="Название категории",
    )
    kind: Kind = Field(
        description="Тип категории",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Продукты",
                "kind": "expense",
            }
        }
    )

    @field_validator("name", mode="before")
    @classmethod
    def _normalize_name(
        cls,
        value: object,
    ) -> object:
        return _strip_name(value)


class CategoryUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="Новое название категории",
    )
    kind: Kind | None = Field(
        default=None,
        description="Новый тип категории",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Супермаркеты",
            }
        }
    )

    @field_validator("name", mode="before")
    @classmethod
    def _normalize_name(
        cls,
        value: object,
    ) -> object:
        return _strip_name(value)

    @model_validator(mode="after")
    def _not_null_columns_stay_not_null(
        self,
    ) -> "CategoryUpdate":
        forbidden = {
            name
            for name in ("name", "kind")
            if (name in self.model_fields_set and getattr(self, name) is None)
        }

        if forbidden:
            raise ValueError(f"нельзя обнулить: {', '.join(sorted(forbidden))}")

        return self


class OperationPageDTO(BaseModel):
    items: list[OperationDTO]
    total: int = Field(
        ge=0,
        description="Общее количество операций",
    )
    page: int = Field(
        ge=1,
        description="Номер текущей страницы",
    )
    limit: int = Field(
        ge=1,
        description="Размер страницы",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [],
                "total": 0,
                "page": 1,
                "limit": 20,
            }
        }
    )


class OperationListQuery(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
    )

    date_from: date | None = Field(
        default=None,
        alias="from",
        description="Начало периода включительно",
        examples=["2026-10-01"],
    )
    date_to: date | None = Field(
        default=None,
        alias="to",
        description="Конец периода включительно",
        examples=["2026-10-31"],
    )
    category_id: UUID | None = Field(
        default=None,
        description="Фильтр по категории",
    )
    kind: Kind | None = Field(
        default=None,
        alias="type",
        description="Фильтр по типу операции",
    )
    page: int = Field(
        default=1,
        ge=1,
        description="Номер страницы",
        examples=[1],
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Количество элементов на странице",
        examples=[20],
    )

    @model_validator(mode="after")
    def _period_is_ordered(
        self,
    ) -> "OperationListQuery":
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_from > self.date_to
        ):
            raise ValueError("from не может быть позже to")

        return self
