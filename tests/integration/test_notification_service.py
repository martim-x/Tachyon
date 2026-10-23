"""Дедупликация уведомлений о бюджетных порогах."""

import logging
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import (
    BudgetThreshold,
    BudgetThresholdReached,
    ThresholdCategory,
)
from app.domains.notification.models import Notification
from app.domains.notification.service import (
    NotificationService,
)
from tests.conftest import UserFactory

pytestmark = pytest.mark.integration

MONTH = date(2026, 10, 1)
OCCURRED_AT = datetime(
    2026,
    10,
    15,
    12,
    tzinfo=UTC,
)


class RecordingNotifier:
    """Тестовый адаптер внешней доставки."""

    def __init__(self) -> None:
        self.sent_ids: list[UUID] = []

    async def send(
        self,
        notification: Notification,
    ) -> None:
        self.sent_ids.append(
            notification.id,
        )


def threshold_event(
    *,
    user_id: UUID,
    threshold: BudgetThreshold,
    categories: tuple[
        ThresholdCategory,
        ...,
    ],
) -> BudgetThresholdReached:
    return BudgetThresholdReached(
        user_id=user_id,
        month=MONTH,
        threshold=threshold,
        categories=categories,
        occurred_at=OCCURRED_AT,
    )


def category(
    *,
    name: str = "Продукты",
    spent: int = 80000,
    limit: int = 100000,
) -> ThresholdCategory:
    return ThresholdCategory(
        category_id=uuid4(),
        category_name=name,
        spent_amount_cents=spent,
        limit_amount_cents=limit,
    )


async def test_creates_one_notification_for_repeated_event(
    session: AsyncSession,
    user_factory: UserFactory,
) -> None:
    user, _token = await user_factory()
    notifier = RecordingNotifier()
    service = NotificationService(
        session,
        notifier,
    )
    products = category()

    event = threshold_event(
        user_id=user.id,
        threshold="WARNING",
        categories=(products,),
    )

    first = await service.handle_budget_threshold(
        event,
    )
    second = await service.handle_budget_threshold(
        event,
    )

    notifications = list(
        (
            await session.scalars(
                select(Notification),
            )
        ).all()
    )

    assert first.id == second.id
    assert len(notifications) == 1
    assert notifications[0].type == "WARNING"
    assert len(notifier.sent_ids) == 1


async def test_combines_categories_into_one_notification(
    session: AsyncSession,
    user_factory: UserFactory,
) -> None:
    user, _token = await user_factory()
    service = NotificationService(session)

    notification = await service.handle_budget_threshold(
        threshold_event(
            user_id=user.id,
            threshold="EXCEEDED",
            categories=(
                category(
                    name="Продукты",
                    spent=120000,
                ),
                category(
                    name="Транспорт",
                    spent=110000,
                ),
            ),
        )
    )

    categories = notification.payload["categories"]

    assert len(categories) == 2
    assert {item["category_name"] for item in categories} == {
        "Продукты",
        "Транспорт",
    }

    notifications = list(
        (
            await session.scalars(
                select(Notification),
            )
        ).all()
    )
    assert len(notifications) == 1


async def test_read_notification_reopens_only_for_new_category(
    session: AsyncSession,
    user_factory: UserFactory,
) -> None:
    user, _token = await user_factory()
    notifier = RecordingNotifier()
    service = NotificationService(
        session,
        notifier,
    )
    products = category(
        name="Продукты",
    )

    notification = await service.handle_budget_threshold(
        threshold_event(
            user_id=user.id,
            threshold="WARNING",
            categories=(products,),
        )
    )

    notification.is_read = True
    await session.flush()

    # Повтор того же превышения не возвращает уведомление в ленту.
    duplicate = await service.handle_budget_threshold(
        threshold_event(
            user_id=user.id,
            threshold="WARNING",
            categories=(products,),
        )
    )

    assert duplicate.is_read is True
    assert len(notifier.sent_ids) == 1

    # Новая категория на том же пороге обновляет существующую строку.
    reopened = await service.handle_budget_threshold(
        threshold_event(
            user_id=user.id,
            threshold="WARNING",
            categories=(
                category(
                    name="Транспорт",
                ),
            ),
        )
    )

    assert reopened.id == notification.id
    assert reopened.is_read is False
    assert len(reopened.payload["categories"]) == 2
    assert len(notifier.sent_ids) == 2


async def test_exceeded_event_is_written_to_log(
    session: AsyncSession,
    user_factory: UserFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    user, _token = await user_factory()
    service = NotificationService(session)

    event = threshold_event(
        user_id=user.id,
        threshold="EXCEEDED",
        categories=(
            category(
                spent=100000,
            ),
        ),
    )

    with caplog.at_level(
        logging.WARNING,
        logger="app.domains.notification.service",
    ):
        await service.handle_budget_threshold(
            event,
        )
        await service.handle_budget_threshold(
            event,
        )

    assert caplog.text.count("budget_limit_exceeded") == 1


async def test_same_threshold_is_isolated_between_users(
    session: AsyncSession,
    user_factory: UserFactory,
) -> None:
    first_user, _first_token = await user_factory()
    second_user, _second_token = await user_factory()
    service = NotificationService(session)

    await service.handle_budget_threshold(
        threshold_event(
            user_id=first_user.id,
            threshold="WARNING",
            categories=(category(),),
        )
    )
    await service.handle_budget_threshold(
        threshold_event(
            user_id=second_user.id,
            threshold="WARNING",
            categories=(category(),),
        )
    )

    notifications = list(
        (
            await session.scalars(
                select(Notification),
            )
        ).all()
    )

    assert len(notifications) == 2
    assert {item.user_id for item in notifications} == {
        first_user.id,
        second_user.id,
    }
