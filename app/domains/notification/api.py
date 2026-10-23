"""HTTP API пользовательских уведомлений."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Path, status

from app.domains.notification.models import Notification
from app.domains.notification.schemas import (
    NotificationDTO,
    NotificationPayloadDTO,
    NotificationType,
)
from app.domains.notification.service import NotificationService
from app.interface.api.deps import CurrentUser, SessionDep
from app.interface.api.schemas import error_responses

router = APIRouter(
    prefix="/api/v1/notifications",
    tags=["Уведомления"],
)

NotificationId = Annotated[
    UUID,
    Path(
        description="Идентификатор уведомления.",
    ),
]


def _notification_dto(
    notification: Notification,
) -> NotificationDTO:
    """Преобразовать модель БД в публичную схему."""

    return NotificationDTO(
        id=notification.id,
        month=notification.month,
        type=cast(
            NotificationType,
            notification.type,
        ),
        payload=NotificationPayloadDTO.model_validate(
            notification.payload,
        ),
        is_read=notification.is_read,
        created_at=notification.created_at,
    )


@router.get(
    "",
    response_model=list[NotificationDTO],
    summary="Получить уведомления",
    description=(
        "Возвращает непрочитанные уведомления текущего пользователя. "
        "Чужие и уже прочитанные уведомления в список не попадают."
    ),
    responses=error_responses(401),
)
async def list_notifications(
    _current_user: CurrentUser,
    session: SessionDep,
) -> list[NotificationDTO]:
    notifications = await NotificationService(
        session,
    ).list_unread()

    return [_notification_dto(notification) for notification in notifications]


@router.patch(
    "/{notification_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Пометить уведомление прочитанным",
    description=(
        "Помечает уведомление текущего пользователя прочитанным. "
        "Чужой или несуществующий UUID возвращает 404."
    ),
    responses=error_responses(
        401,
        404,
        422,
    ),
)
async def mark_notification_read(
    notification_id: NotificationId,
    _current_user: CurrentUser,
    session: SessionDep,
) -> None:
    await NotificationService(
        session,
    ).mark_read(
        notification_id,
    )
