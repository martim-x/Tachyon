from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import FrozenClock
from app.core.user_context import user_scope
from app.domains.reporting.service import ReportingService
from tests.conftest import (
    CategoryFactory,
    LimitFactory,
    LoggedInClient,
    OperationFactory,
    UserFactory,
)

pytestmark = pytest.mark.integration


async def test_monthly_report_returns_totals_categories_and_limits(
    api_client_a: LoggedInClient,
    api_client_b: LoggedInClient,
    category_factory: CategoryFactory,
    operation_factory: OperationFactory,
    limit_factory: LimitFactory,
) -> None:
    food = await category_factory(
        api_client_a.user,
        name="Продукты",
        kind="expense",
    )
    transport = await category_factory(
        api_client_a.user,
        name="Транспорт",
        kind="expense",
    )
    salary = await category_factory(
        api_client_a.user,
        name="Зарплата",
        kind="income",
    )
    foreign_category = await category_factory(
        api_client_b.user,
        name="Чужие расходы",
        kind="expense",
    )

    await operation_factory(
        api_client_a.user,
        Decimal("100.00"),
        category=food,
        kind="expense",
        occurred_at=datetime(2026, 10, 5, 12, tzinfo=UTC),
    )
    await operation_factory(
        api_client_a.user,
        Decimal("50.00"),
        category=transport,
        kind="expense",
        occurred_at=datetime(2026, 10, 10, 12, tzinfo=UTC),
    )
    await operation_factory(
        api_client_a.user,
        Decimal("2000.00"),
        category=salary,
        kind="income",
        occurred_at=datetime(2026, 10, 1, 12, tzinfo=UTC),
    )

    # Эта операция не должна попасть в отчёт пользователя A.
    await operation_factory(
        api_client_b.user,
        Decimal("9999.00"),
        category=foreign_category,
        kind="expense",
        occurred_at=datetime(2026, 10, 5, 12, tzinfo=UTC),
    )

    await limit_factory(
        api_client_a.user,
        Decimal("120.00"),
        month=date(2026, 10, 1),
        category=food,
    )

    response = await api_client_a.client.get(
        "/api/v1/reports/monthly",
        params={
            "from": "2026-10-01",
            "to": "2026-10-31",
            # Неизвестный query-параметр игнорируется.
            "user_id": str(api_client_b.user.id),
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["income"] == "2000.00"
    assert body["expense"] == "150.00"
    assert body["balance"] == "1850.00"
    assert body["forecast_month"] == "2026-10"
    assert body["forecast_basis"] == "dominant_period_month"

    categories = {item["category_name"]: item for item in body["categories"]}

    assert set(categories) == {"Продукты", "Транспорт"}

    assert categories["Продукты"]["amount"] == "100.00"
    assert categories["Продукты"]["share_percent"] == "66.67"
    assert categories["Продукты"]["limit"] == "120.00"
    assert categories["Продукты"]["limit_remaining"] == "20.00"
    assert categories["Продукты"]["limit_exceeded"] is False

    assert categories["Транспорт"]["amount"] == "50.00"
    assert categories["Транспорт"]["share_percent"] == "33.33"
    assert categories["Транспорт"]["limit"] is None


async def test_by_category_shares_equal_one_hundred_percent(
    api_client_a: LoggedInClient,
    category_factory: CategoryFactory,
    operation_factory: OperationFactory,
) -> None:
    first = await category_factory(
        api_client_a.user,
        name="Первая",
        kind="expense",
    )
    second = await category_factory(
        api_client_a.user,
        name="Вторая",
        kind="expense",
    )
    third = await category_factory(
        api_client_a.user,
        name="Третья",
        kind="expense",
    )

    for category in (first, second, third):
        await operation_factory(
            api_client_a.user,
            Decimal("0.01"),
            category=category,
            kind="expense",
            occurred_at=datetime(2026, 10, 15, 12, tzinfo=UTC),
        )

    response = await api_client_a.client.get(
        "/api/v1/reports/by-category",
        params={
            "from": "2026-10-01",
            "to": "2026-10-31",
        },
    )

    assert response.status_code == 200

    shares = [Decimal(item["share_percent"]) for item in response.json()]

    assert sum(shares, start=Decimal("0.00")) == Decimal("100.00")


async def test_empty_report_returns_zeroes_and_dominant_month(
    api_client_a: LoggedInClient,
) -> None:
    response = await api_client_a.client.get(
        "/api/v1/reports/monthly",
        params={
            "from": "2026-10-25",
            "to": "2026-11-20",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "date_from": "2026-10-25",
        "date_to": "2026-11-20",
        "income": "0.00",
        "expense": "0.00",
        "balance": "0.00",
        "categories": [],
        "forecast": "0.00",
        "forecast_month": "2026-11",
        "forecast_basis": "dominant_period_month",
    }


async def test_report_rejects_reversed_period(
    api_client_a: LoggedInClient,
) -> None:
    response = await api_client_a.client.get(
        "/api/v1/reports/monthly",
        params={
            "from": "2026-10-31",
            "to": "2026-10-01",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_monthly_forecast_uses_frozen_clock(
    db_session: async_sessionmaker[AsyncSession],
    user_factory: UserFactory,
    category_factory: CategoryFactory,
    operation_factory: OperationFactory,
) -> None:
    user, _token = await user_factory()
    category = await category_factory(
        user,
        name="Продукты",
        kind="expense",
    )

    await operation_factory(
        user,
        Decimal("100.00"),
        category=category,
        kind="expense",
        occurred_at=datetime(2026, 10, 1, 12, tzinfo=UTC),
    )
    await operation_factory(
        user,
        Decimal("50.00"),
        category=category,
        kind="expense",
        occurred_at=datetime(2026, 10, 10, 12, tzinfo=UTC),
    )
    await operation_factory(
        user,
        Decimal("50.00"),
        category=category,
        kind="expense",
        occurred_at=datetime(2026, 10, 20, 12, tzinfo=UTC),
    )

    async with db_session() as session:
        service = ReportingService(
            session,
            clock=FrozenClock("2026-10-15"),
        )

        with user_scope(user.id):
            report = await service.monthly(
                date_from=date(2026, 9, 25),
                date_to=date(2026, 10, 20),
            )

    assert report.forecast_month == "2026-10"
    assert report.expense == Decimal("200.00")

    # В прогноз попадают только 150.00, потраченные к 15 октября:
    # 150 / 15 * 31 = 310.
    assert report.forecast == Decimal("310.00")


async def test_report_rejects_period_longer_than_five_years(
    api_client_a: LoggedInClient,
) -> None:
    response = await api_client_a.client.get(
        "/api/v1/reports/monthly",
        params={
            "from": "2020-01-01",
            "to": "2026-01-01",
        },
    )

    assert response.status_code == 422

    body = response.json()

    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["detail"] == [
        {
            "field": "to",
            "issue": "Период отчёта не может превышать 5 лет",
        }
    ]


async def test_report_handles_maximum_supported_date(
    api_client_a: LoggedInClient,
) -> None:
    response = await api_client_a.client.get(
        "/api/v1/reports/monthly",
        params={
            "from": "9999-12-31",
            "to": "9999-12-31",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["date_from"] == "9999-12-31"
    assert body["date_to"] == "9999-12-31"
    assert body["income"] == "0.00"
    assert body["expense"] == "0.00"
    assert body["balance"] == "0.00"
    assert body["forecast"] == "0.00"
    assert body["forecast_month"] == "9999-12"
    assert body["categories"] == []
