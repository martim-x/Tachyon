"""События достижения бюджетных лимитов."""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.domains.budget.thresholds import BudgetThresholdService
from tests.conftest import (
    CategoryFactory,
    LimitFactory,
    OperationFactory,
    UserFactory,
)


class RecordingPublisher:
    """Запоминает опубликованные события."""

    def __init__(self) -> None:
        self.events: list[object] = []

    async def publish(
        self,
        event: object,
    ) -> None:
        self.events.append(event)


async def test_publishes_aggregated_threshold_events(
    session: AsyncSession,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
    limit_factory: LimitFactory,
    operation_factory: OperationFactory,
) -> None:
    user, _token = await user_factory()
    products = await category_factory(
        user,
        name="Продукты",
    )
    transport = await category_factory(
        user,
        name="Транспорт",
    )

    await limit_factory(
        user,
        Decimal("1000.00"),
        category=products,
    )
    await limit_factory(
        user,
        Decimal("1000.00"),
        category=transport,
    )

    await operation_factory(
        user,
        Decimal("800.00"),
        category=products,
        occurred_at=datetime(
            2026,
            10,
            10,
            tzinfo=UTC,
        ),
    )
    await operation_factory(
        user,
        Decimal("1200.00"),
        category=transport,
        occurred_at=datetime(
            2026,
            10,
            11,
            tzinfo=UTC,
        ),
    )

    publisher = RecordingPublisher()
    service = BudgetThresholdService(
        session,
        publisher,
        FrozenClock(date(2026, 10, 15)),
    )

    events = await service.evaluate(
        user_id=user.id,
        month=date(2026, 10, 23),
    )

    assert len(events) == 2
    assert publisher.events == list(events)

    warning = next(event for event in events if event.threshold == "WARNING")
    exceeded = next(event for event in events if event.threshold == "EXCEEDED")

    assert warning.month == date(2026, 10, 1)
    assert warning.categories[0].category_name == "Продукты"
    assert warning.categories[0].spent_amount_cents == 80_000

    assert exceeded.categories[0].category_name == "Транспорт"
    assert exceeded.categories[0].spent_amount_cents == 120_000


async def test_combines_multiple_exceeded_categories_into_one_event(
    session: AsyncSession,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
    limit_factory: LimitFactory,
    operation_factory: OperationFactory,
) -> None:
    user, _token = await user_factory()
    first = await category_factory(user, name="Продукты")
    second = await category_factory(user, name="Транспорт")

    for category in (first, second):
        await limit_factory(
            user,
            Decimal("100.00"),
            category=category,
        )
        await operation_factory(
            user,
            Decimal("100.00"),
            category=category,
            occurred_at=datetime(
                2026,
                10,
                10,
                tzinfo=UTC,
            ),
        )

    publisher = RecordingPublisher()
    service = BudgetThresholdService(
        session,
        publisher,
        FrozenClock(date(2026, 10, 15)),
    )

    events = await service.evaluate(
        user_id=user.id,
        month=date(2026, 10, 1),
    )

    assert len(events) == 1
    assert events[0].threshold == "EXCEEDED"
    assert {item.category_name for item in events[0].categories} == {
        "Продукты",
        "Транспорт",
    }


async def test_does_not_publish_for_foreign_user(
    session: AsyncSession,
    user_factory: UserFactory,
    category_factory: CategoryFactory,
    limit_factory: LimitFactory,
    operation_factory: OperationFactory,
) -> None:
    first_user, _token = await user_factory()
    second_user, _token = await user_factory()

    category = await category_factory(first_user)
    await limit_factory(
        first_user,
        Decimal("100.00"),
        category=category,
    )
    await operation_factory(
        first_user,
        Decimal("100.00"),
        category=category,
        occurred_at=datetime(
            2026,
            10,
            10,
            tzinfo=UTC,
        ),
    )

    publisher = RecordingPublisher()
    service = BudgetThresholdService(
        session,
        publisher,
        FrozenClock(date(2026, 10, 15)),
    )

    events = await service.evaluate(
        user_id=second_user.id,
        month=date(2026, 10, 1),
    )

    assert events == ()
    assert publisher.events == []
