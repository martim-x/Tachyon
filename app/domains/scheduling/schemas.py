"""Схемы повторяющихся операций."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

RecurrenceKind = Literal[
    "daily",
    "weekly",
    "monthly",
]


class RecurringRuleBase(BaseModel):
    """Общие поля правила повторяющейся операции."""

    category_id: UUID = Field(
        description="Категория создаваемых операций.",
    )
    kind: RecurrenceKind = Field(
        description="Периодичность: ежедневно, еженедельно или ежемесячно.",
        examples=["monthly"],
    )
    interval: int = Field(
        default=1,
        ge=1,
        description="Количество периодов между запусками.",
        examples=[1],
    )
    amount_cents: int = Field(
        gt=0,
        description="Сумма создаваемой операции в целых копейках.",
        examples=[150000],
    )
    note: str | None = Field(
        default=None,
        max_length=500,
        description="Примечание, добавляемое к операции.",
        examples=["Аренда квартиры"],
    )
    start_date: date = Field(
        description="Дата первого выполнения правила.",
        examples=["2026-10-01"],
    )
    end_date: date | None = Field(
        default=None,
        description="Последняя допустимая дата выполнения правила.",
        examples=["2027-10-01"],
    )


class RecurringRuleCreate(RecurringRuleBase):
    """Данные для создания повторяющегося правила."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "category_id": "34fc6d84-72c0-4ac4-a201-34cf9869ab63",
                    "kind": "monthly",
                    "interval": 1,
                    "amount_cents": 150000,
                    "note": "Аренда квартиры",
                    "start_date": "2026-10-01",
                    "end_date": "2027-10-01",
                }
            ]
        }
    )


class RecurringRuleUpdate(BaseModel):
    """Изменяемые поля повторяющегося правила."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "amount_cents": 160000,
                    "note": "Аренда после индексации",
                    "is_active": True,
                }
            ]
        }
    )

    category_id: UUID | None = Field(
        default=None,
        description="Новая категория создаваемых операций.",
    )
    kind: RecurrenceKind | None = Field(
        default=None,
        description="Новая периодичность правила.",
    )
    interval: int | None = Field(
        default=None,
        ge=1,
        description="Новое количество периодов между запусками.",
    )
    amount_cents: int | None = Field(
        default=None,
        gt=0,
        description="Новая сумма операции в целых копейках.",
    )
    note: str | None = Field(
        default=None,
        max_length=500,
        description="Новое примечание. null очищает примечание.",
    )
    start_date: date | None = Field(
        default=None,
        description="Новая дата начала действия правила.",
    )
    end_date: date | None = Field(
        default=None,
        description="Новая дата окончания. null снимает ограничение.",
    )
    is_active: bool | None = Field(
        default=None,
        description="Признак активности правила.",
    )


class RecurringRuleDTO(RecurringRuleBase):
    """Повторяющееся правило в ответе API."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "2635e13c-cb52-4ed4-88ea-228604caea20",
                    "user_id": "592b92be-7dde-42c3-a311-ce535b26a3dc",
                    "category_id": "34fc6d84-72c0-4ac4-a201-34cf9869ab63",
                    "kind": "monthly",
                    "interval": 1,
                    "amount_cents": 150000,
                    "note": "Аренда квартиры",
                    "start_date": "2026-10-01",
                    "end_date": "2027-10-01",
                    "next_run_at": "2026-11-01T12:00:00Z",
                    "last_run_at": "2026-10-01T12:00:00Z",
                    "is_active": True,
                }
            ]
        },
    )

    id: UUID = Field(
        description="Идентификатор правила.",
    )
    user_id: UUID = Field(
        description="Идентификатор владельца правила.",
    )
    next_run_at: datetime = Field(
        description="Дата и время следующего выполнения.",
    )
    last_run_at: datetime | None = Field(
        description="Дата и время последнего выполнения.",
    )
    is_active: bool = Field(
        description="Признак активности правила.",
    )


class RecurringExecutionDTO(BaseModel):
    """Результат одного выполнения повторяющегося правила."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "f8df1fa8-c94f-4b45-9d56-13e401f60ed8",
                    "rule_id": "2635e13c-cb52-4ed4-88ea-228604caea20",
                    "period_date": "2026-10-01",
                    "operation_id": "cb8c1070-e789-40fb-83b5-bffed44ca11a",
                }
            ]
        },
    )

    id: UUID = Field(
        description="Идентификатор запуска.",
    )
    rule_id: UUID = Field(
        description="Идентификатор обработанного правила.",
    )
    period_date: date = Field(
        description="Период, за который была создана операция.",
    )
    operation_id: UUID | None = Field(
        description=(
            "Идентификатор созданной операции. При предварительном просмотре может отсутствовать."
        ),
    )


class RunRulesRequest(BaseModel):
    """Параметры ручного запуска повторяющихся правил."""

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "from": "2026-10-01",
                    "to": "2026-10-31",
                    "dry_run": True,
                }
            ]
        },
    )

    date_from: date | None = Field(
        default=None,
        alias="from",
        description=(
            "Начало диапазона предварительного просмотра. "
            "Реальный запуск всегда выполняет полный catch-up."
        ),
        examples=["2026-10-01"],
    )
    date_to: date | None = Field(
        default=None,
        alias="to",
        description="Конец диапазона включительно.",
        examples=["2026-10-31"],
    )
    dry_run: bool = Field(
        default=False,
        description=(
            "Если true, возвращает планируемые операции, но ничего не записывает в базу данных."
        ),
    )

    @model_validator(mode="after")
    def validate_period(self) -> "RunRulesRequest":
        """Проверить порядок границ диапазона."""

        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_from > self.date_to
        ):
            raise ValueError("from не может быть позже to")

        return self
