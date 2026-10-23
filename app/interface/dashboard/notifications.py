"""Подготовка уведомлений для Jinja2-шаблонов."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.core.money import Money
from app.domains.notification.models import Notification
from app.interface.dashboard.rendering import ENVIRONMENT

FEED_TEMPLATE = "notifications/feed.html"
PAGE_TEMPLATE = "notifications/page.html"


@dataclass(
    frozen=True,
    slots=True,
)
class NotificationCategoryView:
    """Категория для отображения в уведомлении."""

    name: str
    spent: str
    limit: str


@dataclass(
    frozen=True,
    slots=True,
)
class NotificationView:
    """Уведомление, подготовленное для HTML."""

    id: UUID
    month: date
    type: str
    title: str
    categories: tuple[NotificationCategoryView, ...]


def _money_text(cents: int) -> str:
    """Отформатировать целые копейки без float."""

    return f"{Money.from_cents(cents).amount:.2f}"


def _notification_view(
    notification: Notification,
) -> NotificationView:
    categories: list[NotificationCategoryView] = []

    raw_categories = notification.payload.get(
        "categories",
        [],
    )

    if isinstance(raw_categories, list):
        for item in raw_categories:
            if not isinstance(item, dict):
                continue

            name = item.get("category_name")
            spent = item.get("spent_amount_cents")
            limit = item.get("limit_amount_cents")

            if (
                not isinstance(name, str)
                or not isinstance(spent, int)
                or isinstance(spent, bool)
                or not isinstance(limit, int)
                or isinstance(limit, bool)
            ):
                continue

            categories.append(
                NotificationCategoryView(
                    name=name,
                    spent=_money_text(spent),
                    limit=_money_text(limit),
                )
            )

    title = "Лимит превышен" if notification.type == "EXCEEDED" else "Достигнуто 80% лимита"

    return NotificationView(
        id=notification.id,
        month=notification.month,
        type=notification.type,
        title=title,
        categories=tuple(categories),
    )


def render_notification_feed(
    notifications: Sequence[Notification],
) -> str:
    """Отрисовать HTML-фрагмент ленты."""

    return ENVIRONMENT.get_template(
        FEED_TEMPLATE,
    ).render(
        notifications=[_notification_view(notification) for notification in notifications],
    )


def render_notification_page(
    notifications: Sequence[Notification],
) -> str:
    """Отрисовать полную страницу уведомлений."""

    return ENVIRONMENT.get_template(
        PAGE_TEMPLATE,
    ).render(
        notifications=[_notification_view(notification) for notification in notifications],
    )
