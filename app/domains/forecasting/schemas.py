"""DTO прогноза расходов."""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ForecastDTO(BaseModel):
    """Прогноз расходов на выбранный месяц."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "year": 2026,
                    "month": 10,
                    "pace": "WHOLE_MONTH",
                    "days_in_month": 31,
                    "days_elapsed": 15,
                    "days_remaining": 16,
                    "spent_to_date": "700.00",
                    "daily_rate": "46.67",
                    "projected_total": "1446.67",
                    "low_confidence": False,
                }
            ]
        }
    )

    year: int = Field(
        description="Год прогноза.",
        examples=[2026],
    )
    month: int = Field(
        ge=1,
        le=12,
        description="Номер месяца прогноза.",
        examples=[10],
    )
    pace: str = Field(
        description="Использованная стратегия расчёта темпа.",
        examples=["WHOLE_MONTH"],
    )
    days_in_month: int = Field(
        ge=28,
        le=31,
        description="Количество календарных дней в месяце.",
    )
    days_elapsed: int = Field(
        ge=0,
        description="Количество прошедших дней месяца.",
    )
    days_remaining: int = Field(
        ge=0,
        description="Количество оставшихся дней месяца.",
    )
    spent_to_date: Decimal = Field(
        decimal_places=2,
        description="Фактические расходы на дату расчёта.",
        examples=["700.00"],
    )
    daily_rate: Decimal = Field(
        decimal_places=2,
        description="Средний дневной темп расходов.",
        examples=["46.67"],
    )
    projected_total: Decimal = Field(
        decimal_places=2,
        description="Прогнозируемые расходы к окончанию месяца.",
        examples=["1446.67"],
    )
    low_confidence: bool = Field(
        description=("Признак низкой достоверности из-за недостаточного количества данных."),
    )
