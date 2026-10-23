"""Сквозной сценарий создания бюджетных уведомлений."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import FrozenClock
from app.core.money import Money
from app.domains.notification.models import Notification
from app.domains.scheduling.ports import create_operation_impl
from tests.conftest import (
    CategoryFactory,
    LimitFactory,
    LoggedInClient,
    UserFactory,
)

pytestmark = pytest.mark.integration

OCTOBER = date(2026, 10, 1)


async def notifications_for(
    sessions: async_sessionmaker[AsyncSession],
    user_id: UUID,
) -> list[Notification]:
    """Получить уведомления пользователя напрямую из тестовой БД."""
    async with sessions() as session:
        result = await session.scalars(
            select(Notification)
            .where(
                Notification.user_id == user_id,
            )
            .order_by(
                Notification.type,
            )
        )

        return list(result.all())


async def create_expense(
    client: LoggedInClient,
    *,
    category_id: UUID,
    amount: str,
    occurred_at: str = "2026-10-10T12:00:00Z",
) -> None:
    """Создать расход через настоящий HTTP API."""
    response = await client.client.post(
        "/api/v1/operations",
        json={
            "category_id": str(category_id),
            "amount": amount,
            "kind": "expense",
            "occurred_at": occurred_at,
        },
    )

    assert response.status_code == 201, response.text


async def test_manual_operations_trigger_thresholds_without_duplicates(
    db_session: async_sessionmaker[AsyncSession],
    api_client_a: LoggedInClient,
    category_factory: CategoryFactory,
    limit_factory: LimitFactory,
) -> None:
    """79,99% ничего не создаёт, 80% даёт WARNING, 100% — EXCEEDED."""
    category = await category_factory(
        api_client_a.user,
        name="Продукты",
    )
    await limit_factory(
        api_client_a.user,
        Decimal("1000.00"),
        month=OCTOBER,
        category=category,
    )

    # 79,99% от 1000.00 — порог ещё не достигнут.
    await create_expense(
        api_client_a,
        category_id=category.id,
        amount="799.90",
    )

    notifications = await notifications_for(
        db_session,
        api_client_a.user.id,
    )
    assert notifications == []

    # Добавляем 0.10: итог ровно 800.00, то есть 80%.
    await create_expense(
        api_client_a,
        category_id=category.id,
        amount="0.10",
    )

    notifications = await notifications_for(
        db_session,
        api_client_a.user.id,
    )

    assert len(notifications) == 1
    assert notifications[0].type == "WARNING"
    assert notifications[0].month == OCTOBER
    assert notifications[0].payload["categories"][0]["category_name"] == "Продукты"
    assert notifications[0].payload["categories"][0]["spent_amount_cents"] == 80_000

    # Итог становится ровно 1000.00 — создаётся EXCEEDED.
    await create_expense(
        api_client_a,
        category_id=category.id,
        amount="200.00",
    )

    notifications = await notifications_for(
        db_session,
        api_client_a.user.id,
    )

    assert len(notifications) == 2
    assert {notification.type for notification in notifications} == {
        "WARNING",
        "EXCEEDED",
    }

    exceeded = next(
        notification for notification in notifications if notification.type == "EXCEEDED"
    )

    assert exceeded.payload["categories"][0]["spent_amount_cents"] == 100_000
    assert exceeded.payload["categories"][0]["limit_amount_cents"] == 100_000

    # Повторное срабатывание EXCEEDED обновляет строку, но не создаёт дубль.
    await create_expense(
        api_client_a,
        category_id=category.id,
        amount="1.00",
    )

    notifications = await notifications_for(
        db_session,
        api_client_a.user.id,
    )

    assert len(notifications) == 2

    exceeded = next(
        notification for notification in notifications if notification.type == "EXCEEDED"
    )
    assert exceeded.payload["categories"][0]["spent_amount_cents"] == 100_100


async def test_future_operation_does_not_trigger_notification(
    db_session: async_sessionmaker[AsyncSession],
    api_client_a: LoggedInClient,
    category_factory: CategoryFactory,
    limit_factory: LimitFactory,
) -> None:
    """Операция после FrozenClock не считается фактической тратой."""
    category = await category_factory(
        api_client_a.user,
        name="Будущие расходы",
    )
    await limit_factory(
        api_client_a.user,
        Decimal("100.00"),
        month=OCTOBER,
        category=category,
    )

    # Общий frozen_clock проекта установлен на 15 октября.
    await create_expense(
        api_client_a,
        category_id=category.id,
        amount="100.00",
        occurred_at="2026-10-20T12:00:00Z",
    )

    notifications = await notifications_for(
        db_session,
        api_client_a.user.id,
    )

    assert notifications == []


async def test_recurring_operation_triggers_notification(
    db_session: async_sessionmaker[AsyncSession],
    user_factory: UserFactory,
    category_factory: CategoryFactory,
    limit_factory: LimitFactory,
) -> None:
    """Операция планировщика проходит через ту же проверку бюджета."""
    user, _token = await user_factory()
    category = await category_factory(
        user,
        name="Подписки",
    )
    await limit_factory(
        user,
        Decimal("100.00"),
        month=OCTOBER,
        category=category,
    )

    async with db_session() as session:
        await create_operation_impl(
            session,
            user_id=user.id,
            category_id=category.id,
            amount=Money(Decimal("80.00")),
            kind="expense",
            occurred_at=datetime(
                2026,
                10,
                10,
                12,
                tzinfo=UTC,
            ),
            recurring_execution_id=uuid4(),
            note="Подписка",
            source="recurring",
            clock=FrozenClock(date(2026, 10, 15)),
        )
        await session.commit()

    notifications = await notifications_for(
        db_session,
        user.id,
    )

    assert len(notifications) == 1
    assert notifications[0].type == "WARNING"
    assert notifications[0].payload["categories"][0]["category_name"] == "Подписки"


async def test_notifications_remain_isolated_between_users(
    db_session: async_sessionmaker[AsyncSession],
    api_client_a: LoggedInClient,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
    limit_factory: LimitFactory,
) -> None:
    """Расход другого пользователя не создаёт уведомление первому."""
    second_user, _token = await user_factory(
        "second-notification-user@test.io",
    )
    second_category = await category_factory(
        second_user,
        name="Чужая категория",
    )
    await limit_factory(
        second_user,
        Decimal("100.00"),
        month=OCTOBER,
        category=second_category,
    )

    async with db_session() as session:
        await create_operation_impl(
            session,
            user_id=second_user.id,
            category_id=second_category.id,
            amount=Money(Decimal("100.00")),
            kind="expense",
            occurred_at=datetime(
                2026,
                10,
                10,
                12,
                tzinfo=UTC,
            ),
            recurring_execution_id=uuid4(),
            clock=FrozenClock(date(2026, 10, 15)),
        )
        await session.commit()

    first_notifications = await notifications_for(
        db_session,
        api_client_a.user.id,
    )
    second_notifications = await notifications_for(
        db_session,
        second_user.id,
    )

    assert first_notifications == []
    assert len(second_notifications) == 1
    assert second_notifications[0].type == "EXCEEDED"
