from decimal import Decimal
from uuid import UUID

import pytest

from app.domains.reporting.queries import (
    ReportRow,
    aggregate_report,
)

pytestmark = pytest.mark.unit

FOOD_ID = UUID("10000000-0000-0000-0000-000000000001")
TRANSPORT_ID = UUID("10000000-0000-0000-0000-000000000002")
OTHER_ID = UUID("10000000-0000-0000-0000-000000000003")


def test_aggregate_report_calculates_totals_and_limits() -> None:
    report = aggregate_report(
        [
            ReportRow(
                category_id=FOOD_ID,
                category_name="Продукты",
                kind="expense",
                amount_cents=10_000,
                limit_cents=12_000,
            ),
            ReportRow(
                category_id=TRANSPORT_ID,
                category_name="Транспорт",
                kind="expense",
                amount_cents=5_000,
                limit_cents=4_000,
            ),
            ReportRow(
                category_id=OTHER_ID,
                category_name="Зарплата",
                kind="income",
                amount_cents=200_000,
            ),
        ]
    )

    assert report.income == Decimal("2000.00")
    assert report.expense == Decimal("150.00")
    assert report.balance == Decimal("1850.00")

    assert len(report.categories) == 2

    food = report.categories[0]
    transport = report.categories[1]

    assert food.category_name == "Продукты"
    assert food.amount == Decimal("100.00")
    assert food.share_percent == Decimal("66.67")
    assert food.limit == Decimal("120.00")
    assert food.limit_remaining == Decimal("20.00")
    assert food.limit_percent == Decimal("83.33")
    assert food.limit_exceeded is False

    assert transport.category_name == "Транспорт"
    assert transport.amount == Decimal("50.00")
    assert transport.share_percent == Decimal("33.33")
    assert transport.limit == Decimal("40.00")
    assert transport.limit_remaining == Decimal("-10.00")
    assert transport.limit_percent == Decimal("125.00")
    assert transport.limit_exceeded is True


def test_equal_categories_have_exactly_one_hundred_percent() -> None:
    report = aggregate_report(
        [
            ReportRow(
                category_id=FOOD_ID,
                category_name="А",
                kind="expense",
                amount_cents=1,
            ),
            ReportRow(
                category_id=TRANSPORT_ID,
                category_name="Б",
                kind="expense",
                amount_cents=1,
            ),
            ReportRow(
                category_id=OTHER_ID,
                category_name="В",
                kind="expense",
                amount_cents=1,
            ),
        ]
    )

    shares = [item.share_percent for item in report.categories]

    assert shares == [
        Decimal("33.34"),
        Decimal("33.33"),
        Decimal("33.33"),
    ]
    assert sum(shares, start=Decimal("0.00")) == Decimal("100.00")


def test_operation_without_category_is_not_lost() -> None:
    report = aggregate_report(
        [
            ReportRow(
                category_id=None,
                category_name=None,
                kind="expense",
                amount_cents=2_500,
            )
        ]
    )

    assert report.expense == Decimal("25.00")
    assert len(report.categories) == 1
    assert report.categories[0].category_id is None
    assert report.categories[0].category_name == "Без категории"
    assert report.categories[0].amount == Decimal("25.00")
    assert report.categories[0].share_percent == Decimal("100.00")


def test_empty_period_returns_zeroes() -> None:
    report = aggregate_report([])

    assert report.income == Decimal("0.00")
    assert report.expense == Decimal("0.00")
    assert report.balance == Decimal("0.00")
    assert report.categories == ()


def test_income_only_has_no_expense_categories() -> None:
    report = aggregate_report(
        [
            ReportRow(
                category_id=OTHER_ID,
                category_name="Зарплата",
                kind="income",
                amount_cents=75_000,
            )
        ]
    )

    assert report.income == Decimal("750.00")
    assert report.expense == Decimal("0.00")
    assert report.balance == Decimal("750.00")
    assert report.categories == ()
