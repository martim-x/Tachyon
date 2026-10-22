"""DTO прогноза (docs/02 §forecasting, docs/03 §S6.2, docs/06 §Формулы).

Чистое ядро: без SQLAlchemy, FastAPI, float — только Decimal и даты.
"""

from decimal import Decimal

from pydantic import BaseModel


class ForecastDTO(BaseModel):
    """Прогноз расходов на месяц (docs/03 §S6.2, docs/06 §Формулы)."""

    year: int
    month: int
    pace: str
    days_in_month: int
    days_elapsed: int
    days_remaining: int
    spent_to_date: Decimal
    daily_rate: Decimal
    projected_total: Decimal
    low_confidence: bool