"""Integration tests for /api/v1/forecast (docs/03 §S6.5 T1, docs/06 §Формулы).

Names contain 'forecast' keyword for `pytest -k forecast` and 'isolation' for
`pytest -k isolation` as required by docs/06 §Структура тестов.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from tests.conftest import CategoryFactory, LoggedInClient, OperationFactory

pytestmark = pytest.mark.integration


async def test_forecast_endpoint_returns_zeros_for_empty_user(
    api_client_a: LoggedInClient,
) -> None:
    """docs/06 §Нулевые траты: GET /api/v1/forecast?month=2026-10 → 200,
    spent_to_date=0.00, daily_rate=0.00, projected_total=0.00, low_confidence=true.
    """
    client: AsyncClient = api_client_a.client
    resp = await client.get("/api/v1/forecast", params={"month": "2026-10"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["spent_to_date"] == "0.00"
    assert data["daily_rate"] == "0.00"
    assert data["projected_total"] == "0.00"
    # docs/06 §Нулевые траты: пустой пользователь → low_confidence=true
    assert data["low_confidence"] is True
    assert data["year"] == 2026
    assert data["month"] == 10


async def test_forecast_endpoint_returns_month_forecast(
    api_client_a: LoggedInClient,
    category_factory: CategoryFactory,
    operation_factory: OperationFactory,
) -> None:
    """AC9 WHOLE_MONTH: spent=600.00, days_elapsed=15 → daily_rate=40.00,
    projected_total=1240.00 (15 дней * 40 + 600).
    """
    cat = await category_factory(api_client_a.user)
    await operation_factory(
        api_client_a.user,
        amount=Decimal("100.00"),
        category=cat,
        occurred_at=datetime(2026, 10, 1, tzinfo=UTC),
    )
    await operation_factory(
        api_client_a.user,
        amount=Decimal("100.00"),
        category=cat,
        occurred_at=datetime(2026, 10, 5, tzinfo=UTC),
    )
    await operation_factory(
        api_client_a.user,
        amount=Decimal("400.00"),
        category=cat,
        occurred_at=datetime(2026, 10, 10, tzinfo=UTC),
    )
    # 600 spent by 2026-10-15 (FROZEN_TODAY)
    # spent_to_date = 600.00, days_elapsed=15, daily_rate=40.00, projected=600 + 40*16 = 1240.00

    client: AsyncClient = api_client_a.client
    resp = await client.get("/api/v1/forecast", params={"month": "2026-10"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["spent_to_date"] == "600.00"
    assert data["daily_rate"] == "40.00"
    assert data["projected_total"] == "1240.00"
    assert data["days_elapsed"] == 15
    assert data["days_remaining"] == 16
    assert data["low_confidence"] is False
    assert data["pace"] == "WHOLE_MONTH"


async def test_forecast_endpoint_recent_window_pace(
    api_client_a: LoggedInClient,
    category_factory: CategoryFactory,
    operation_factory: OperationFactory,
) -> None:
    """AC10 RECENT_WINDOW: spent=600.00, recent 7 days sum=490.00 →
    daily_rate=70.00 (490/7), projected_total=1720.00.
    """
    cat = await category_factory(api_client_a.user)
    # 110 spent before the 7-day window (10.10 is outside window 09-15)
    await operation_factory(
        api_client_a.user,
        amount=Decimal("110.00"),
        category=cat,
        occurred_at=datetime(2026, 10, 1, tzinfo=UTC),
    )
    # 490 in the last 7 days (09.10-15.10)
    await operation_factory(
        api_client_a.user,
        amount=Decimal("490.00"),
        category=cat,
        occurred_at=datetime(2026, 10, 12, tzinfo=UTC),
    )

    client: AsyncClient = api_client_a.client
    resp = await client.get(
        "/api/v1/forecast",
        params={"month": "2026-10", "pace": "RECENT_WINDOW"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["spent_to_date"] == "600.00"
    assert data["daily_rate"] == "70.00"
    assert data["projected_total"] == "1720.00"
    assert data["pace"] == "RECENT_WINDOW"
    assert data["low_confidence"] is False


async def test_forecast_endpoint_future_month_returns_zeros(
    api_client_a: LoggedInClient,
) -> None:
    """AC12: future month (2026-12) → days_elapsed=0, projected=0, low_confidence=true."""
    client: AsyncClient = api_client_a.client
    resp = await client.get("/api/v1/forecast", params={"month": "2026-12"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["spent_to_date"] == "0.00"
    assert data["daily_rate"] == "0.00"
    assert data["projected_total"] == "0.00"
    assert data["days_elapsed"] == 0
    assert data["days_remaining"] == 31  # December has 31 days
    assert data["low_confidence"] is True  # days_elapsed=0 < 3


async def test_forecast_endpoint_rejects_invalid_month(
    api_client_a: LoggedInClient,
) -> None:
    """Invalid month format/year/month → 422 ValidationError."""
    client: AsyncClient = api_client_a.client

    # Invalid format
    resp = await client.get("/api/v1/forecast", params={"month": "2026-1"})
    assert resp.status_code == 422

    # Month 13
    resp = await client.get("/api/v1/forecast", params={"month": "2026-13"})
    assert resp.status_code == 422

    # Year 0000 (out of range)
    resp = await client.get("/api/v1/forecast", params={"month": "0000-01"})
    assert resp.status_code == 422

    # Year 9999 (out of range)
    resp = await client.get("/api/v1/forecast", params={"month": "9999-12"})
    assert resp.status_code == 422

    # Year 10000
    resp = await client.get("/api/v1/forecast", params={"month": "10000-01"})
    assert resp.status_code == 422


async def test_forecast_endpoint_isolation_ignores_other_user_operations(
    api_client_a: LoggedInClient,
    api_client_b: LoggedInClient,
    category_factory: CategoryFactory,
    operation_factory: OperationFactory,
) -> None:
    """Isolation: Bob's operations must not appear in Alice's forecast."""
    # Alice has 100.00 expense
    cat_a = await category_factory(api_client_a.user)
    await operation_factory(
        api_client_a.user,
        amount=Decimal("100.00"),
        category=cat_a,
        occurred_at=datetime(2026, 10, 10, tzinfo=UTC),
    )

    # Bob has 9999.00 expense in same month
    cat_b = await category_factory(api_client_b.user)
    await operation_factory(
        api_client_b.user,
        amount=Decimal("9999.00"),
        category=cat_b,
        occurred_at=datetime(2026, 10, 10, tzinfo=UTC),
    )

    client_a: AsyncClient = api_client_a.client
    resp = await client_a.get("/api/v1/forecast", params={"month": "2026-10"})
    assert resp.status_code == 200
    data = resp.json()
    # Only Alice's 100.00, not Bob's 9999.00
    assert data["spent_to_date"] == "100.00"


async def test_forecast_endpoint_requires_authentication() -> None:
    """Unauthenticated request → 401."""
    from tests.conftest import create_app

    application = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://test",
    ) as client:
        resp = await client.get("/api/v1/forecast", params={"month": "2026-10"})
        assert resp.status_code == 401


async def test_forecast_endpoint_pace_rejects_invalid_value(
    api_client_a: LoggedInClient,
) -> None:
    """Invalid pace value → 422."""
    client: AsyncClient = api_client_a.client
    resp = await client.get("/api/v1/forecast", params={"month": "2026-10", "pace": "INVALID"})
    assert resp.status_code == 422
