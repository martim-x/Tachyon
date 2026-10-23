"""HTML-страница уведомлений для dashboard."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path
from fastapi.responses import HTMLResponse

from app.domains.notification.service import NotificationService
from app.interface.api.deps import CurrentUser, SessionDep
from app.interface.dashboard.notifications import (
    render_notification_page,
)

router = APIRouter(
    prefix="/dashboard/notifications",
    include_in_schema=False,
)

NotificationId = Annotated[
    UUID,
    Path(
        description="Идентификатор уведомления.",
    ),
]


@router.get(
    "",
    response_class=HTMLResponse,
)
async def notification_page(
    _current_user: CurrentUser,
    session: SessionDep,
) -> HTMLResponse:
    """Показать страницу непрочитанных уведомлений."""

    notifications = await NotificationService(
        session,
    ).list_unread()

    return HTMLResponse(
        render_notification_page(
            notifications,
        )
    )


@router.patch(
    "/{notification_id}/read",
    response_class=HTMLResponse,
)
async def mark_dashboard_notification_read(
    notification_id: NotificationId,
    _current_user: CurrentUser,
    session: SessionDep,
) -> HTMLResponse:
    """Закрыть уведомление через HTMX."""

    await NotificationService(
        session,
    ).mark_read(
        notification_id,
    )

    # Пустой ответ заменяет карточку через hx-swap="outerHTML".
    return HTMLResponse("")
