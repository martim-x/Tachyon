import pytest

from app.core.events import BudgetThreshold
from app.domains.budget.service import reached_threshold


@pytest.mark.parametrize(
    ("limit_amount_cents", "spent_amount_cents", "expected"),
    [
        (10_000, 0, None),
        (10_000, 7_999, None),
        (10_000, 8_000, "WARNING"),
        (10_000, 9_999, "WARNING"),
        (10_000, 10_000, "EXCEEDED"),
        (10_000, 12_500, "EXCEEDED"),
        (0, 10_000, None),
        (-1, 10_000, None),
    ],
)
def test_reached_threshold(
    limit_amount_cents: int,
    spent_amount_cents: int,
    expected: BudgetThreshold | None,
) -> None:
    assert (
        reached_threshold(
            limit_amount_cents,
            spent_amount_cents,
        )
        == expected
    )
