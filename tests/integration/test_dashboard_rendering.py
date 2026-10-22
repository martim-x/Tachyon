"""Интеграционные тесты рендеринга диаграммы из данных домена (S10.1 T3).

Данные собираются фабриками из десяточного каркаса (docs/06 §Фикстуры):
user_factory / category_factory / operation_factory. Рендеринг вызывается
на точках реальной агрегации TT-26 (``ReportingService.by_category``),
а не на собранных вручную списках, поэтому двойное наполнение pandas
отсутствует (NFR-3).
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.user_context import user_scope
from app.domains.reporting.service import ReportingService
from app.interface.dashboard.rendering import (
    render_category_chart,
    render_category_dashboard,
)
from tests.conftest import (
    CategoryFactory,
    OperationFactory,
    UserFactory,
)

pytestmark = pytest.mark.integration


async def user_category_points(
    user,
    session_maker: async_sessionmaker[AsyncSession],
    date_from: date,
    date_to: date,
):
    """Точки агрегации TT-26 для пользователя (фильтр из UserContext)."""

    async with session_maker() as session:
        service = ReportingService(session)
        with user_scope(user.id):
            return await service.by_category(
                date_from=date_from,
                date_to=date_to,
            )


def occurrence(day: int) -> datetime:
    """Операция внутри октябрьского периода: дата фиксирована, не «сегодня»."""

    return datetime(2026, 10, day, 12, tzinfo=UTC)


async def test_render_category_chart_from_domain_aggregation(
    user_factory: UserFactory,
    category_factory: CategoryFactory,
    operation_factory: OperationFactory,
    db_session: async_sessionmaker[AsyncSession],
) -> None:
    user, _token = await user_factory()
    food = await category_factory(user, name="Продукты", kind="expense")
    transport = await category_factory(user, name="Транспорт", kind="expense")

    await operation_factory(
        user,
        Decimal("100.00"),
        category=food,
        occurred_at=occurrence(5),
    )
    await operation_factory(
        user,
        Decimal("50.00"),
        category=transport,
        occurred_at=occurrence(10),
    )

    points = await user_category_points(
        user,
        db_session,
        date(2026, 10, 1),
        date(2026, 10, 31),
    )
    html = render_category_chart(
        points,
        date_from=date(2026, 10, 1),
        date_to=date(2026, 10, 31),
    )

    assert "category-chart__bar" in html
    assert "Продукты" in html
    assert "Транспорт" in html
    assert "66.67%" in html
    assert "33.33%" in html
    assert "150.00" in html
    assert "100.00%" in html
    assert "data-percent=\"66.67\"" in html


async def test_rendering_isolation_alice_chart_has_no_bob_categories(
    user_factory: UserFactory,
    category_factory: CategoryFactory,
    operation_factory: OperationFactory,
    db_session: async_sessionmaker[AsyncSession],
) -> None:
    alice, _alice_token = await user_factory("alice@test.io")
    bob, _bob_token = await user_factory("bob@test.io")

    own = await category_factory(alice, name="Продукты", kind="expense")
    foreign = await category_factory(bob, name="Траты Боба", kind="expense")

    await operation_factory(
        alice,
        Decimal("10.00"),
        category=own,
        occurred_at=occurrence(5),
    )
    await operation_factory(
        bob,
        Decimal("9999.00"),
        category=foreign,
        occurred_at=occurrence(6),
    )

    alice_points = await user_category_points(
        alice,
        db_session,
        date(2026, 10, 1),
        date(2026, 10, 31),
    )
    alice_html = render_category_chart(
        alice_points,
        date_from=date(2026, 10, 1),
        date_to=date(2026, 10, 31),
    )

    bob_points = await user_category_points(
        bob,
        db_session,
        date(2026, 10, 1),
        date(2026, 10, 31),
    )
    bob_html = render_category_chart(
        bob_points,
        date_from=date(2026, 10, 1),
        date_to=date(2026, 10, 31),
    )

    assert "Траты Боба" not in alice_html
    assert "9999.00" not in alice_html
    assert "Продукты" not in bob_html


async def test_render_category_chart_empty_state_without_operations(
    user_factory: UserFactory,
    category_factory: CategoryFactory,
    db_session: async_sessionmaker[AsyncSession],
) -> None:
    user, _token = await user_factory()
    await category_factory(user, name="Пустая", kind="expense")

    points = await user_category_points(
        user,
        db_session,
        date(2026, 10, 1),
        date(2026, 10, 31),
    )
    html = render_category_chart(
        points,
        date_from=date(2026, 10, 1),
        date_to=date(2026, 10, 31),
    )

    assert "Расходов за выбранный период нет" in html
    assert "category-chart__bar" not in html


async def test_render_category_dashboard_includes_period_and_component(
    user_factory: UserFactory,
    category_factory: CategoryFactory,
    operation_factory: OperationFactory,
    db_session: async_sessionmaker[AsyncSession],
) -> None:
    user, _token = await user_factory()
    food = await category_factory(user, name="Кафе", kind="expense")
    await operation_factory(
        user,
        Decimal("12.34"),
        category=food,
        occurred_at=occurrence(3),
    )

    points = await user_category_points(
        user,
        db_session,
        date(2026, 10, 1),
        date(2026, 10, 31),
    )
    html = render_category_dashboard(
        points,
        date_from=date(2026, 10, 1),
        date_to=date(2026, 10, 31),
    )

    assert "<!doctype html>" in html
    assert "Период: 2026-10-01 — 2026-10-31" in html
    assert "category-chart__bar" in html
    assert "Кафе" in html
    assert "12.34" in html


async def test_render_category_chart_folds_more_than_seven_categories(
    user_factory: UserFactory,
    category_factory: CategoryFactory,
    operation_factory: OperationFactory,
    db_session: async_sessionmaker[AsyncSession],
) -> None:
    user, _token = await user_factory()

    categories = [
        await category_factory(user, name=f"Категория {index}", kind="expense")
        for index in range(1, 9)
    ]
    for index, category in enumerate(categories):
        await operation_factory(
            user,
            Decimal(f"{100 - index}.00"),
            category=category,
            occurred_at=occurrence(5 + index),
        )

    points = await user_category_points(
        user,
        db_session,
        date(2026, 10, 1),
        date(2026, 10, 31),
    )
    html = render_category_chart(
        points,
        date_from=date(2026, 10, 1),
        date_to=date(2026, 10, 31),
    )

    assert "Прочие" in html
    assert "Категория 1" in html
    assert "Категория 8" not in html


async def test_render_category_chart_escapes_category_markup(
    user_factory: UserFactory,
    category_factory: CategoryFactory,
    operation_factory: OperationFactory,
    db_session: async_sessionmaker[AsyncSession],
) -> None:
    user, _token = await user_factory()
    suspicious = await category_factory(
        user,
        name="<script>Продукты</script>",
        kind="expense",
    )
    await operation_factory(
        user,
        Decimal("10.00"),
        category=suspicious,
        occurred_at=occurrence(5),
    )

    points = await user_category_points(
        user,
        db_session,
        date(2026, 10, 1),
        date(2026, 10, 31),
    )
    html = render_category_chart(
        points,
        date_from=date(2026, 10, 1),
        date_to=date(2026, 10, 31),
    )

    assert "&lt;script&gt;Продукты&lt;/script&gt;" in html
    assert "<script>" not in html
