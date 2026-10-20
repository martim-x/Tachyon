from decimal import ROUND_HALF_UP, Decimal
from enum import Enum, auto


class LimitStatus(Enum):
    OK = auto()
    WARNING = auto()
    EXCEEDED = auto()
    EXCEEDED_PROJECTED = auto()


LIMIT_WARNING_RATIO = Decimal("0.8")

def limit_status(limit: Decimal | None, spent: Decimal, projected: Decimal) -> LimitStatus:
    """Возвращает статус лимита:
    - ОК: даже с учетом прогноза не превышает лимит
    - WARNING: прогноз превышает 80%, но пока не превышен
    - EXCEEDED: потраченное превышает лимит
    - EXCEEDED_PROJECTED: прогноз превышает лимит
    1. Если spent >= limit -> EXCEEDED
    2. Иначе, если projected > limit -> EXCEEDED_PROJECTED
    3. Иначе считаем процент от факта: percent = spent / limit.
       Если percent >= 0.8 → WARNING.
    4. Иначе -> OK
    """
    if limit is None or limit <= 0:
        return LimitStatus.OK

    if spent >= limit:
        return LimitStatus.EXCEEDED

    if projected >= limit:
        return LimitStatus.EXCEEDED_PROJECTED

    percent = (spent / limit).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    if percent >= LIMIT_WARNING_RATIO:
        return LimitStatus.WARNING


    return LimitStatus.OK
