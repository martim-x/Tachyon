"""API-схемы аналитических отчётов."""

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class SeriesPointDTO(BaseModel):
    """Одна категория для отчёта или диаграммы."""

    category_id: UUID | None = Field(
        description="Идентификатор категории или null для «Без категории»"
    )
    category_name: str = Field(description="Название категории")
    amount: Decimal = Field(
        decimal_places=2,
        description="Сумма расходов категории",
    )
    share_percent: Decimal = Field(
        ge=0,
        le=100,
        decimal_places=2,
        description="Доля категории в расходах, %",
    )
    limit: Decimal | None = Field(
        default=None,
        decimal_places=2,
        description="Лимит категории в выбранном месяце",
    )
    limit_remaining: Decimal | None = Field(
        default=None,
        decimal_places=2,
        description="Остаток лимита; отрицательный при превышении",
    )
    limit_percent: Decimal | None = Field(
        default=None,
        ge=0,
        decimal_places=2,
        description="Использованная доля лимита, %",
    )
    limit_exceeded: bool = Field(description="Достигнут или превышен лимит")

    model_config = {
        "json_schema_extra": {
            "example": {
                "category_id": "10000000-0000-0000-0000-000000000001",
                "category_name": "Продукты",
                "amount": "1250.50",
                "share_percent": "62.53",
                "limit": "2000.00",
                "limit_remaining": "749.50",
                "limit_percent": "62.53",
                "limit_exceeded": False,
            }
        }
    }


class ReportDTO(BaseModel):
    """Полный финансовый отчёт за период."""

    date_from: date = Field(description="Начало отчётного периода включительно")
    date_to: date = Field(description="Конец отчётного периода включительно")
    income: Decimal = Field(
        decimal_places=2,
        description="Доходы за период",
    )
    expense: Decimal = Field(
        decimal_places=2,
        description="Расходы за период",
    )
    balance: Decimal = Field(
        decimal_places=2,
        description="Доходы минус расходы",
    )
    categories: list[SeriesPointDTO] = Field(description="Разбивка расходов по категориям")
    forecast: Decimal = Field(
        decimal_places=2,
        description="Прогноз расходов для выбранного месяца",
    )
    forecast_month: str = Field(
        pattern=r"^\d{4}-(0[1-9]|1[0-2])$",
        description="Месяц, использованный для прогноза",
    )
    forecast_basis: Literal["dominant_period_month"] = Field(
        default="dominant_period_month",
        description=("Прогноз рассчитан по месяцу, содержащему большую часть периода"),
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "date_from": "2026-10-01",
                "date_to": "2026-10-31",
                "income": "50000.00",
                "expense": "20000.00",
                "balance": "30000.00",
                "categories": [],
                "forecast": "21333.33",
                "forecast_month": "2026-10",
                "forecast_basis": "dominant_period_month",
            }
        }
    }
