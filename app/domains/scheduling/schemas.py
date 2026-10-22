"""Схемы повторяющихся операций (docs/03 §S4.1-4.2)."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Kind = Literal["daily", "weekly", "monthly"]


class RecurringRuleBase(BaseModel):
    category_id: UUID
    kind: Kind
    interval: int = Field(default=1, ge=1)
    amount_cents: int = Field(gt=0)
    note: str | None = Field(default=None, max_length=500)
    start_date: date
    end_date: date | None = None


class RecurringRuleCreate(RecurringRuleBase):
    pass


class RecurringRuleUpdate(BaseModel):
    category_id: UUID | None = None
    kind: Kind | None = None
    interval: int | None = Field(default=None, ge=1)
    amount_cents: int | None = Field(default=None, gt=0)
    note: str | None = Field(default=None, max_length=500)
    start_date: date | None = None
    end_date: date | None = None
    is_active: bool | None = None


class RecurringRuleDTO(RecurringRuleBase):
    id: UUID
    user_id: UUID
    next_run_at: datetime
    last_run_at: datetime | None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class RecurringExecutionDTO(BaseModel):
    id: UUID
    rule_id: UUID
    period_date: date
    operation_id: UUID | None

    model_config = ConfigDict(from_attributes=True)


class RunRulesRequest(BaseModel):
    """Диапазон ручного запуска повторяющихся правил."""

    date_from: date | None = Field(
        default=None,
        alias="from",
        description=(
            "Начало диапазона предварительного просмотра. "
            "Реальный запуск всегда выполняет полный catch-up."
        ),
    )
    date_to: date | None = Field(
        default=None,
        alias="to",
        description="Конец диапазона включительно",
    )
    dry_run: bool = Field(
        default=False,
        description="Только показать результат без записи в БД",
    )

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "from": "2026-10-01",
                "to": "2026-10-31",
                "dry_run": True,
            }
        },
    )

    @model_validator(mode="after")
    def validate_period(self) -> "RunRulesRequest":
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_from > self.date_to
        ):
            raise ValueError("from не может быть позже to")

        return self
