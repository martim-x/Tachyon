"""HTML-лента пользовательских уведомлений."""

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.user_context import user_scope
from app.domains.notification.models import Notification
from app.domains.notification.repository import NotificationRepository
from tests.conftest import LoggedInClient

pytestmark = pytest.mark.integration


async def create_dashboard_notification(
    sessions: async_sessionmaker[AsyncSession],
    *,
    user_id: UUID,
    category_name: str,
) -> UUID:
    """Создать тестовое уведомление."""

    async with sessions() as session:
        with user_scope(user_id):
            notification = await NotificationRepository(
                session,
            ).create(
                month=date(2026, 10, 1),
                type="EXCEEDED",
                payload={
                    "categories": [
                        {
                            "category_id": str(uuid4()),
                            "category_name": category_name,
                            "spent_amount_cents": 120000,
                            "limit_amount_cents": 100000,
                        }
                    ]
                },
                is_read=False,
                created_at=datetime(
                    2026,
                    10,
                    15,
                    12,
                    tzinfo=UTC,
                ),
            )

        await session.commit()

        return notification.id


async def test_dashboard_shows_only_own_notifications(
    db_session: async_sessionmaker[AsyncSession],
    api_client_a: LoggedInClient,
    api_client_b: LoggedInClient,
) -> None:
    own_id = await create_dashboard_notification(
        db_session,
        user_id=api_client_a.user.id,
        category_name="Продукты",
    )
    await create_dashboard_notification(
        db_session,
        user_id=api_client_b.user.id,
        category_name="Чужая категория",
    )

    response = await api_client_a.client.get(
        "/dashboard/notifications",
    )

    assert response.status_code == 200
    assert "Продукты" in response.text
    assert "Чужая категория" not in response.text
    assert f"/dashboard/notifications/{own_id}/read" in response.text
    assert 'hx-swap="outerHTML"' in response.text
    assert "1200.00 ₽" in response.text
    assert "1000.00 ₽" in response.text


async def test_empty_dashboard_has_message(
    api_client_a: LoggedInClient,
) -> None:
    response = await api_client_a.client.get(
        "/dashboard/notifications",
    )

    assert response.status_code == 200
    assert "Новых уведомлений нет." in response.text


async def test_htmx_action_marks_notification_read(
    db_session: async_sessionmaker[AsyncSession],
    api_client_a: LoggedInClient,
) -> None:
    notification_id = await create_dashboard_notification(
        db_session,
        user_id=api_client_a.user.id,
        category_name="Транспорт",
    )

    response = await api_client_a.client.patch(
        f"/dashboard/notifications/{notification_id}/read",
        headers={
            "HX-Request": "true",
        },
    )

    assert response.status_code == 200
    assert response.text == ""

    page_response = await api_client_a.client.get(
        "/dashboard/notifications",
    )

    assert "Транспорт" not in page_response.text
    assert "Новых уведомлений нет." in page_response.text

    async with db_session() as session:
        notification = await session.scalar(
            select(Notification).where(
                Notification.id == notification_id,
            )
        )

    assert notification is not None
    assert notification.is_read is True


async def test_cannot_close_foreign_dashboard_notification(
    db_session: async_sessionmaker[AsyncSession],
    api_client_a: LoggedInClient,
    api_client_b: LoggedInClient,
) -> None:
    notification_id = await create_dashboard_notification(
        db_session,
        user_id=api_client_b.user.id,
        category_name="Чужая категория",
    )

    response = await api_client_a.client.patch(
        f"/dashboard/notifications/{notification_id}/read",
        headers={
            "HX-Request": "true",
        },
    )

    assert response.status_code == 404
