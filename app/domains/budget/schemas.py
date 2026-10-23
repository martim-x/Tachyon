"""Схемы бюджетных лимитов и их текущего состояния."""

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

BudgetStatus = Literal[
    "OK",
    "WARNING",
    "EXCEEDED",
    "EXCEEDED_PROJECTED",
]


class LimitCreate(BaseModel):
    """Данные для создания месячного лимита категории."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "category_id": "34fc6d84-72c0-4ac4-a201-34cf9869ab63",
                    "month": "2026-10-01",
                    "limit_amount_cents": 500000,
                }
            ]
        }
    )

    category_id: UUID = Field(
        description="Идентификатор категории пользователя.",
    )
    month: date = Field(
        description=(
            "Месяц действия лимита. Допускается любая дата месяца; "
            "она нормализуется к первому числу."
        ),
    )
    limit_amount_cents: int = Field(
        gt=0,
        description="Размер лимита в целых копейках.",
        examples=[500000],
    )

    @field_validator("month")
    @classmethod
    def month_starts_on_first_day(
        cls,
        value: date,
    ) -> date:
        """Нормализовать месяц к первому числу."""

        return value.replace(day=1)


class LimitRead(BaseModel):
    """Созданный бюджетный лимит."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "examples": [
                {
                    "user_id": "592b92be-7dde-42c3-a311-ce535b26a3dc",
                    "category_id": "34fc6d84-72c0-4ac4-a201-34cf9869ab63",
                    "month": "2026-10-01",
                    "limit_amount_cents": 500000,
                }
            ]
        },
    )

    user_id: UUID = Field(
        description="Идентификатор владельца лимита.",
    )
    category_id: UUID = Field(
        description="Идентификатор категории.",
    )
    month: date = Field(
        description="Первый день месяца действия лимита.",
    )
    limit_amount_cents: int = Field(
        description="Размер лимита в целых копейках.",
    )


class LimitStatusDTO(BaseModel):
    """Фактическое и прогнозируемое состояние бюджетного лимита."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "category_id": "34fc6d84-72c0-4ac4-a201-34cf9869ab63",
                    "month": "2026-10-01",
                    "limit_amount_cents": 100000,
                    "spent_amount_cents": 70000,
                    "remaining_amount_cents": 30000,
                    "projected_amount_cents": 144667,
                    "percent": "0.7000",
                    "status": "EXCEEDED_PROJECTED",
                }
            ]
        }
    )

    category_id: UUID = Field(
        description="Идентификатор категории.",
    )
    month: date = Field(
        description="Первый день месяца действия лимита.",
    )
    limit_amount_cents: int = Field(
        description="Размер лимита в целых копейках.",
    )
    spent_amount_cents: int = Field(
        description="Фактические расходы в целых копейках.",
    )
    remaining_amount_cents: int = Field(
        description="Остаток лимита в целых копейках.",
    )
    projected_amount_cents: int = Field(
        description="Прогноз расходов к окончанию месяца в целых копейках.",
    )
    percent: Decimal = Field(
        description="Доля использованного лимита без потери точности.",
        examples=["0.7000"],
    )
    status: BudgetStatus = Field(
        description=("Состояние лимита: OK, WARNING, EXCEEDED или EXCEEDED_PROJECTED."),
    )
