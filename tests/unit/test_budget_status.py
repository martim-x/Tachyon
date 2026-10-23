from decimal import Decimal

import pytest

from app.domains.budget.service import LimitStatus, limit_status


@pytest.mark.parametrize(
    "limit, spent, projected, expected",
    [
        (Decimal("500"), Decimal("400"), Decimal("420"), LimitStatus.WARNING),
        (Decimal("500"), Decimal("500"), Decimal("480"), LimitStatus.EXCEEDED),
        (Decimal("500"), Decimal("510"), Decimal("490"), LimitStatus.EXCEEDED),
        (Decimal("500"), Decimal("450"), Decimal("900"), LimitStatus.EXCEEDED_PROJECTED),
        (Decimal("500"), Decimal("300"), Decimal("350"), LimitStatus.OK),
    ],
)
def test_status_limit(limit, spent, projected, expected):
    assert limit_status(limit, spent, projected) == expected
