"""API пользовательских уведомлений."""

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.user_context import user_scope
from app.domains.notification.models import Notification
from app.domains.notification.repository import NotificationRepository
from tests.conftest import (
    ApiClientFactory,
    LoggedInClient,
)

pytestmark = pytest.mark.integration

MONTH = date(2026, 10, 1)
CREATED_AT = datetime(
    2026,
    10,
    15,
    12,
    tzinfo=UTC,
)


async def create_notification(
    sessions: async_sessionmaker[AsyncSession],
    *,
    user_id: UUID,
    notification_type: str = "WARNING",
    is_read: bool = False,
    category_name: str = "Продукты",
) -> UUID:
    """Создать уведомление через ScopedRepository."""

    async with sessions() as session:
        with user_scope(user_id):
            notification = await NotificationRepository(
                session,
            ).create(
                month=MONTH,
                type=notification_type,
                payload={
                    "categories": [
                        {
                            "category_id": str(uuid4()),
                            "category_name": category_name,
                            "spent_amount_cents": 80000,
                            "limit_amount_cents": 100000,
                        }
                    ]
                },
                is_read=is_read,
                created_at=CREATED_AT,
            )

        await session.commit()

        return notification.id


async def test_empty_notification_list_returns_200(
    api_client_a: LoggedInClient,
) -> None:
    response = await api_client_a.client.get(
        "/api/v1/notifications",
    )

    assert response.status_code == 200
    assert response.json() == []


async def test_lists_only_current_users_unread_notifications(
    db_session: async_sessionmaker[AsyncSession],
    api_client_a: LoggedInClient,
    api_client_b: LoggedInClient,
) -> None:
    own_id = await create_notification(
        db_session,
        user_id=api_client_a.user.id,
        category_name="Продукты",
    )
    await create_notification(
        db_session,
        user_id=api_client_a.user.id,
        notification_type="EXCEEDED",
        is_read=True,
        category_name="Прочитанное",
    )
    await create_notification(
        db_session,
        user_id=api_client_b.user.id,
        category_name="Чужое",
    )

    response = await api_client_a.client.get(
        "/api/v1/notifications",
    )

    assert response.status_code == 200

    body = response.json()

    assert len(body) == 1
    assert body[0]["id"] == str(own_id)
    assert body[0]["type"] == "WARNING"
    assert body[0]["is_read"] is False
    assert body[0]["payload"]["categories"][0]["category_name"] == "Продукты"


async def test_marks_own_notification_read(
    db_session: async_sessionmaker[AsyncSession],
    api_client_a: LoggedInClient,
) -> None:
    notification_id = await create_notification(
        db_session,
        user_id=api_client_a.user.id,
    )

    response = await api_client_a.client.patch(
        f"/api/v1/notifications/{notification_id}/read",
    )

    assert response.status_code == 204
    assert response.content == b""

    list_response = await api_client_a.client.get(
        "/api/v1/notifications",
    )

    assert list_response.status_code == 200
    assert list_response.json() == []

    async with db_session() as session:
        notification = await session.scalar(
            select(Notification).where(
                Notification.id == notification_id,
            )
        )

    assert notification is not None
    assert notification.is_read is True


async def test_cannot_mark_foreign_notification_read(
    db_session: async_sessionmaker[AsyncSession],
    api_client_a: LoggedInClient,
    api_client_b: LoggedInClient,
) -> None:
    notification_id = await create_notification(
        db_session,
        user_id=api_client_b.user.id,
    )

    response = await api_client_a.client.patch(
        f"/api/v1/notifications/{notification_id}/read",
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"

    async with db_session() as session:
        notification = await session.scalar(
            select(Notification).where(
                Notification.id == notification_id,
            )
        )

    assert notification is not None
    assert notification.is_read is False


async def test_notifications_require_authorization(
    api_client: ApiClientFactory,
) -> None:
    anonymous_client = api_client()

    list_response = await anonymous_client.get(
        "/api/v1/notifications",
    )
    read_response = await anonymous_client.patch(
        f"/api/v1/notifications/{uuid4()}/read",
    )

    assert list_response.status_code == 401
    assert read_response.status_code == 401
