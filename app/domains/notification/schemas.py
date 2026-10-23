"""Схемы API пользовательских уведомлений."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

NotificationType = Literal[
    "WARNING",
    "EXCEEDED",
]


class NotificationCategoryDTO(BaseModel):
    """Категория, достигшая порога лимита."""

    category_id: UUID = Field(
        description="Идентификатор категории.",
    )
    category_name: str = Field(
        description="Название категории.",
    )
    spent_amount_cents: int = Field(
        ge=0,
        description="Фактические расходы в целых копейках.",
    )
    limit_amount_cents: int = Field(
        gt=0,
        description="Размер лимита в целых копейках.",
    )


class NotificationPayloadDTO(BaseModel):
    """Данные уведомления о бюджетном лимите."""

    categories: list[NotificationCategoryDTO] = Field(
        description="Категории, достигшие указанного порога.",
    )


class NotificationDTO(BaseModel):
    """Уведомление текущего пользователя."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "21e714a4-1159-4b82-b32d-53a3549e263e",
                "month": "2026-10-01",
                "type": "EXCEEDED",
                "payload": {
                    "categories": [
                        {
                            "category_id": "38eb7fd2-e544-4520-8de1-266cc4050d85",
                            "category_name": "Продукты",
                            "spent_amount_cents": 120000,
                            "limit_amount_cents": 100000,
                        }
                    ]
                },
                "is_read": False,
                "created_at": "2026-10-15T12:00:00Z",
            }
        }
    )

    id: UUID
    month: date
    type: NotificationType
    payload: NotificationPayloadDTO
    is_read: bool
    created_at: datetime
