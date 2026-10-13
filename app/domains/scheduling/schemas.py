"""Схемы повторяющихся операций (docs/03 §S4.1-4.2)."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

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