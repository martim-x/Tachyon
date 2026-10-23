"""Доступ к уведомлениям текущего пользователя."""

from datetime import date
from uuid import UUID

from app.core.persistence.scoped_repository import ScopedRepository
from app.domains.notification.models import Notification


class NotificationRepository(
    ScopedRepository[Notification],
):
    """Уведомления с обязательным пользовательским scope."""

    model = Notification

    async def get_for_threshold(
        self,
        *,
        month: date,
        threshold: str,
    ) -> Notification | None:
        """Найти уведомление пользователя за месяц и порог."""

        statement = self._scoped().where(
            Notification.month == month,
            Notification.type == threshold,
        )
        result = await self._session.execute(
            statement,
        )

        return result.scalar_one_or_none()

    async def list_unread(
        self,
    ) -> list[Notification]:
        """Получить непрочитанные уведомления, новые первыми."""

        statement = (
            self._scoped()
            .where(
                Notification.is_read.is_(False),
            )
            .order_by(
                Notification.created_at.desc(),
            )
        )
        result = await self._session.execute(
            statement,
        )

        return list(
            result.scalars().all(),
        )

    async def mark_read(
        self,
        notification_id: UUID,
    ) -> Notification:
        """Пометить своё уведомление прочитанным."""

        notification = await self.get_or_404(
            notification_id,
        )
        notification.is_read = True
        await self._session.flush()

        return notification
