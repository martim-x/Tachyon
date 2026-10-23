"""Асинхронная шина и контракты доменных событий."""

from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Protocol, TypeVar, cast
from uuid import UUID

EventT = TypeVar(
    "EventT",
    bound=object,
)

EventHandler = Callable[
    [object],
    Awaitable[None],
]

BudgetThreshold = Literal[
    "WARNING",
    "EXCEEDED",
]


@dataclass(
    frozen=True,
    slots=True,
)
class ThresholdCategory:
    """Категория, достигшая порога бюджетного лимита."""

    category_id: UUID
    category_name: str
    spent_amount_cents: int
    limit_amount_cents: int


@dataclass(
    frozen=True,
    slots=True,
)
class BudgetThresholdReached:
    """Один или несколько лимитов достигли заданного порога."""

    user_id: UUID
    month: date
    threshold: BudgetThreshold
    categories: tuple[
        ThresholdCategory,
        ...,
    ]
    occurred_at: datetime

    def __post_init__(self) -> None:
        if self.month.day != 1:
            raise ValueError("month должен быть первым днём месяца")

        if not self.categories:
            raise ValueError("Событие должно содержать хотя бы одну категорию")


class EventPublisher(Protocol):
    """Порт публикации доменных событий."""

    async def publish(
        self,
        event: object,
    ) -> None:
        """Опубликовать событие подписанным обработчикам."""

        ...


class EventBus(EventPublisher):
    """Внутрипроцессная асинхронная шина событий."""

    def __init__(self) -> None:
        self._handlers: dict[
            type[object],
            list[EventHandler],
        ] = defaultdict(list)

    def subscribe(
        self,
        event_type: type[EventT],
        handler: Callable[
            [EventT],
            Awaitable[None],
        ],
    ) -> None:
        """Подписать обработчик на конкретный тип события."""

        self._handlers[event_type].append(
            cast(
                EventHandler,
                handler,
            )
        )

    async def publish(
        self,
        event: object,
    ) -> None:
        """Последовательно вызвать обработчики события."""

        handlers = tuple(
            self._handlers.get(
                type(event),
                (),
            )
        )

        for handler in handlers:
            await handler(event)
