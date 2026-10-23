from decimal import Decimal
from enum import Enum, auto

from app.core.events import BudgetThreshold


class LimitStatus(Enum):
    OK = auto()
    WARNING = auto()
    EXCEEDED = auto()
    EXCEEDED_PROJECTED = auto()


LIMIT_WARNING_RATIO = Decimal("0.8")


def limit_status(limit: Decimal | None, spent: Decimal, projected: Decimal) -> LimitStatus:
    """Возвращает статус в порядке приоритета.

    EXCEEDED: фактические расходы достигли лимита или превысили его.
    EXCEEDED_PROJECTED: прогноз строго превышает лимит.
    WARNING: фактические расходы достигли 80% лимита.
    OK: остальные случаи, включая отсутствие положительного лимита.
    """
    if limit is None or limit <= 0:
        return LimitStatus.OK

    if spent >= limit:
        return LimitStatus.EXCEEDED

    if projected > limit:
        return LimitStatus.EXCEEDED_PROJECTED

    if spent >= limit * LIMIT_WARNING_RATIO:
        return LimitStatus.WARNING

    return LimitStatus.OK


def reached_threshold(
    limit_amount_cents: int,
    spent_amount_cents: int,
) -> BudgetThreshold | None:
    """Определить достигнутый порог по фактическим расходам.

    EXCEEDED имеет приоритет над WARNING. Расчёт выполняется в целых
    копейках без float, чтобы границы 80% и 100% были точными.
    """
    if limit_amount_cents <= 0:
        return None

    if spent_amount_cents >= limit_amount_cents:
        return "EXCEEDED"

    if spent_amount_cents * 100 >= limit_amount_cents * 80:
        return "WARNING"

    return None
