"""Создание и дедупликация пользовательских уведомлений."""

import logging
from typing import Protocol
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import (
    BudgetThresholdReached,
    ThresholdCategory,
)
from app.core.user_context import user_scope
from app.domains.notification.models import Notification
from app.domains.notification.repository import (
    NotificationRepository,
)

logger = logging.getLogger(__name__)


class Notifier(Protocol):
    """Порт внешней доставки созданного уведомления."""

    async def send(
        self,
        notification: Notification,
    ) -> None:
        """Доставить уведомление через подключённый адаптер."""

        ...


class NullNotifier:
    """Адаптер по умолчанию: уведомление доступно через БД и API."""

    async def send(
        self,
        notification: Notification,
    ) -> None:
        del notification


class NotificationService:
    """Сохраняет одно уведомление на порог в месяц."""

    def __init__(
        self,
        session: AsyncSession,
        notifier: Notifier | None = None,
    ) -> None:
        self._session = session
        self._repository = NotificationRepository(
            session,
        )
        self._notifier = notifier or NullNotifier()

    async def list_unread(
        self,
    ) -> list[Notification]:
        """Получить непрочитанные уведомления текущего пользователя."""

        return await self._repository.list_unread()

    async def mark_read(
        self,
        notification_id: UUID,
    ) -> Notification:
        """Пометить своё уведомление прочитанным."""

        return await self._repository.mark_read(
            notification_id,
        )

    async def handle_budget_threshold(
        self,
        event: BudgetThresholdReached,
    ) -> Notification:
        """Обработать доверенное внутреннее событие budget."""

        with user_scope(event.user_id):
            notification = await self._record_threshold(
                event,
            )

        return notification

    async def _record_threshold(
        self,
        event: BudgetThresholdReached,
    ) -> Notification:
        existing = await self._repository.get_for_threshold(
            month=event.month,
            threshold=event.threshold,
        )

        if existing is not None:
            return await self._merge_existing(
                existing,
                event.categories,
            )

        try:
            async with self._session.begin_nested():
                notification = await self._repository.create(
                    month=event.month,
                    type=event.threshold,
                    payload={
                        "categories": self._category_payload(
                            event.categories,
                        ),
                    },
                    is_read=False,
                    created_at=event.occurred_at,
                )
        except IntegrityError:
            # Другой конкурентный обработчик уже создал ту же запись.
            existing = await self._repository.get_for_threshold(
                month=event.month,
                threshold=event.threshold,
            )

            if existing is None:
                raise

            return await self._merge_existing(
                existing,
                event.categories,
            )

        # Лог пишется только после фактического создания новой записи.
        self._log_exceeded(
            notification,
            event.categories,
        )

        await self._notifier.send(
            notification,
        )

        return notification

    async def _merge_existing(
        self,
        notification: Notification,
        categories: tuple[
            ThresholdCategory,
            ...,
        ],
    ) -> Notification:
        current_categories = notification.payload.get(
            "categories",
            [],
        )

        categories_by_id = {
            str(item["category_id"]): item
            for item in current_categories
            if isinstance(item, dict) and "category_id" in item
        }

        new_category_added = False

        for item in self._category_payload(
            categories,
        ):
            category_id = str(
                item["category_id"],
            )

            if category_id not in categories_by_id:
                new_category_added = True

            categories_by_id[category_id] = item

        notification.payload = {
            "categories": sorted(
                categories_by_id.values(),
                key=lambda item: str(
                    item["category_name"],
                ),
            ),
        }

        # Прочитанное уведомление возвращается только при появлении
        # новой категории, впервые достигшей того же порога.
        if new_category_added:
            notification.is_read = False

        await self._session.flush()

        if new_category_added:
            # Новая категория является новым фактом превышения.
            self._log_exceeded(
                notification,
                categories,
            )

            await self._notifier.send(
                notification,
            )

        return notification

    @staticmethod
    def _log_exceeded(
        notification: Notification,
        categories: tuple[
            ThresholdCategory,
            ...,
        ],
    ) -> None:
        """Записать в лог только новое фактическое превышение."""

        if notification.type != "EXCEEDED":
            return

        logger.warning(
            "budget_limit_exceeded",
            extra={
                "user_id": str(
                    notification.user_id,
                ),
                "month": notification.month.isoformat(),
                "categories": [category.category_name for category in categories],
            },
        )

    @staticmethod
    def _category_payload(
        categories: tuple[
            ThresholdCategory,
            ...,
        ],
    ) -> list[dict[str, object]]:
        return [
            {
                "category_id": str(
                    category.category_id,
                ),
                "category_name": category.category_name,
                "spent_amount_cents": (category.spent_amount_cents),
                "limit_amount_cents": (category.limit_amount_cents),
            }
            for category in categories
        ]
