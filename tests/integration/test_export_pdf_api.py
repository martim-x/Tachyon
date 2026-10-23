"""Integration tests for /api/v1/reports/monthly/export/pdf.

PDF-экспорт (docs/03 §S7.2): 200 + application/pdf + первые байты %PDF,
длинный период ломается на страницы, операции пользователя B не попадают
в PDF пользователя A. Имена тестов содержат 'export' и 'isolation' для
`pytest -k export|isolation` (docs/06 §Структура тестов).
"""

import re
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from tests.conftest import CategoryFactory, LoggedInClient, OperationFactory

pytestmark = pytest.mark.integration

PAGE_PATTERN = re.compile(rb"/Type\s*/Page[^s]")


def page_count(payload: bytes) -> int:
    """Число страниц по объектам PDF: страницы лежат вне контентных потоков."""

    return len(PAGE_PATTERN.findall(payload))


async def test_export_pdf_endpoint_returns_pdf_file(
    api_client_a: LoggedInClient,
) -> None:
    """Пустой период: 200, application/pdf, %PDF, имя файла с периодом."""
    client: AsyncClient = api_client_a.client
    resp = await client.get(
        "/api/v1/reports/monthly/export/pdf",
        params={"from": "2026-10-01", "to": "2026-10-31"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF-")
    assert resp.content.rstrip().endswith(b"%%EOF")
    assert resp.headers["content-disposition"] == (
        'attachment; filename="report-20261001-20261031.pdf"'
    )
    assert page_count(resp.content) >= 1


async def test_export_pdf_contains_user_amounts_as_strings(
    api_client_a: LoggedInClient,
    category_factory: CategoryFactory,
    operation_factory: OperationFactory,
) -> None:
    """Суммы пользователя A лежат в PDF точными строками из Decimal.

    У каждой суммы свой «цент», поэтому строка однозначно указывает на
    свой показатель и не является подстрокой соседней.
    """
    food = await category_factory(api_client_a.user, name="Продукты", kind="expense")
    transport = await category_factory(api_client_a.user, name="Транспорт", kind="expense")
    salary = await category_factory(api_client_a.user, name="Зарплата", kind="income")

    await operation_factory(
        api_client_a.user,
        Decimal("2000.07"),
        category=salary,
        kind="income",
        occurred_at=datetime(2026, 10, 1, 12, tzinfo=UTC),
    )
    await operation_factory(
        api_client_a.user,
        Decimal("100.13"),
        category=food,
        occurred_at=datetime(2026, 10, 5, 12, tzinfo=UTC),
    )
    await operation_factory(
        api_client_a.user,
        Decimal("50.21"),
        category=transport,
        occurred_at=datetime(2026, 10, 10, 12, tzinfo=UTC),
    )

    client: AsyncClient = api_client_a.client
    resp = await client.get(
        "/api/v1/reports/monthly/export/pdf",
        params={"from": "2026-10-01", "to": "2026-10-31"},
    )
    assert resp.status_code == 200

    for amount in (b"2000.07", b"150.34", b"1849.73", b"100.13", b"50.21"):
        assert amount in resp.content


async def test_export_pdf_empty_period_returns_headers_only(
    api_client_a: LoggedInClient,
) -> None:
    """Период без операций: файл формируется, суммы нулевые."""
    client: AsyncClient = api_client_a.client
    resp = await client.get(
        "/api/v1/reports/monthly/export/pdf",
        params={"from": "2026-10-25", "to": "2026-11-20"},
    )
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF-")
    assert b"0.00" in resp.content
    assert page_count(resp.content) >= 1


async def test_export_pdf_long_period_splits_into_pages(
    api_client_a: LoggedInClient,
    category_factory: CategoryFactory,
    operation_factory: OperationFactory,
) -> None:
    """Длинный период: категорийная таблица переносится на страницы.

    Полтора десятка категорий гарантированно не входят в один экран,
    LongTable повторяет шапку на каждой странице (без наезда строк).
    """
    for index in range(150):
        category = await category_factory(
            api_client_a.user,
            name=f"Категория {index:03d}",
            kind="expense",
        )
        await operation_factory(
            api_client_a.user,
            Decimal(f"{index + 1}.55"),
            category=category,
            occurred_at=datetime(2026, 3, 15, 12, tzinfo=UTC),
        )

    client: AsyncClient = api_client_a.client
    resp = await client.get(
        "/api/v1/reports/monthly/export/pdf",
        params={"from": "2026-03-01", "to": "2026-08-31"},
    )
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF-")

    assert page_count(resp.content) >= 2
    assert b"1.55" in resp.content
    assert b"149.55" in resp.content
    assert b"150.55" in resp.content


async def test_export_pdf_isolation_excludes_other_user_operations(
    api_client_a: LoggedInClient,
    api_client_b: LoggedInClient,
    category_factory: CategoryFactory,
    operation_factory: OperationFactory,
) -> None:
    """Isolation: операции Bob не попадают в PDF Alice."""
    category_a = await category_factory(api_client_a.user, name="Продукты", kind="expense")
    category_b = await category_factory(api_client_b.user, name="Продукты", kind="expense")

    await operation_factory(
        api_client_a.user,
        Decimal("100.00"),
        category=category_a,
        occurred_at=datetime(2026, 10, 5, 12, tzinfo=UTC),
    )
    await operation_factory(
        api_client_b.user,
        Decimal("9999.00"),
        category=category_b,
        occurred_at=datetime(2026, 10, 5, 12, tzinfo=UTC),
    )

    client: AsyncClient = api_client_a.client
    resp = await client.get(
        "/api/v1/reports/monthly/export/pdf",
        params={"from": "2026-10-01", "to": "2026-10-31"},
    )
    assert resp.status_code == 200

    assert b"100.00" in resp.content
    assert b"9999.00" not in resp.content


async def test_export_pdf_rejects_reversed_period(
    api_client_a: LoggedInClient,
) -> None:
    """Reversed период → 422 VALIDATION_ERROR, как у /monthly."""
    client: AsyncClient = api_client_a.client
    resp = await client.get(
        "/api/v1/reports/monthly/export/pdf",
        params={"from": "2026-10-31", "to": "2026-10-01"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_export_pdf_requires_authentication() -> None:
    """Без токена → 401."""
    from tests.conftest import create_app

    application = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=application),
        base_url="http://test",
    ) as client:
        resp = await client.get(
            "/api/v1/reports/monthly/export/pdf",
            params={"from": "2026-10-01", "to": "2026-10-31"},
        )
        assert resp.status_code == 401
