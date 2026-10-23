"""Модель пользовательских уведомлений."""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.persistence import Base


class Notification(Base):
    """Одно уведомление на пользователя, месяц и порог."""

    __tablename__ = "notifications"

    __table_args__ = (
        CheckConstraint(
            "type IN ('WARNING', 'EXCEEDED')",
            name="notification_type",
        ),
        UniqueConstraint(
            "user_id",
            "month",
            "type",
            name="uq_notifications_user_month_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"),
        index=True,
    )
    month: Mapped[date] = mapped_column(
        Date,
    )
    type: Mapped[str] = mapped_column(
        String(50),
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSON,
    )
    is_read: Mapped[bool] = mapped_column(
        default=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
