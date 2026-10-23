"""Тесты внутренней шины доменных событий."""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from app.core.events import (
    BudgetThresholdReached,
    EventBus,
    ThresholdCategory,
)


@dataclass(frozen=True)
class SampleEvent:
    value: int


async def test_event_bus_delivers_event_to_subscriber() -> None:
    bus = EventBus()
    received: list[int] = []

    async def handle(
        event: SampleEvent,
    ) -> None:
        received.append(event.value)

    bus.subscribe(
        SampleEvent,
        handle,
    )

    await bus.publish(
        SampleEvent(value=42),
    )

    assert received == [42]


async def test_event_bus_ignores_unrelated_events() -> None:
    bus = EventBus()
    received: list[int] = []

    async def handle(
        event: SampleEvent,
    ) -> None:
        received.append(event.value)

    bus.subscribe(
        SampleEvent,
        handle,
    )

    await bus.publish(
        object(),
    )

    assert received == []


def test_budget_threshold_event_contains_categories() -> None:
    category_id = uuid4()
    user_id = uuid4()

    event = BudgetThresholdReached(
        user_id=user_id,
        month=date(2026, 10, 1),
        threshold="EXCEEDED",
        categories=(
            ThresholdCategory(
                category_id=category_id,
                category_name="Продукты",
                spent_amount_cents=100000,
                limit_amount_cents=100000,
            ),
        ),
        occurred_at=datetime(
            2026,
            10,
            15,
            12,
            tzinfo=UTC,
        ),
    )

    assert event.user_id == user_id
    assert event.threshold == "EXCEEDED"
    assert event.categories[0].category_id == category_id
    assert event.categories[0].spent_amount_cents == 100000


def test_budget_threshold_event_requires_normalized_month() -> None:
    with pytest.raises(
        ValueError,
        match="первым днём",
    ):
        BudgetThresholdReached(
            user_id=uuid4(),
            month=date(2026, 10, 15),
            threshold="WARNING",
            categories=(
                ThresholdCategory(
                    category_id=uuid4(),
                    category_name="Транспорт",
                    spent_amount_cents=8000,
                    limit_amount_cents=10000,
                ),
            ),
            occurred_at=datetime.now(UTC),
        )


def test_budget_threshold_event_requires_categories() -> None:
    with pytest.raises(
        ValueError,
        match="хотя бы одну категорию",
    ):
        BudgetThresholdReached(
            user_id=uuid4(),
            month=date(2026, 10, 1),
            threshold="WARNING",
            categories=(),
            occurred_at=datetime.now(UTC),
        )
