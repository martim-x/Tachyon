"""Add notification deduplication.

Revision ID: 515e2ddc9426
Revises: dc3b03584f96
Create Date: 2026-10-23 16:41:34.447873
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "515e2ddc9426"
down_revision: str | Sequence[str] | None = "dc3b03584f96"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _normalized_type(value: object) -> str | None:
    """Привести старые значения типа к новому контракту."""

    normalized = str(value).strip().upper()

    if normalized in {
        "WARNING",
        "LIMIT_WARNING",
        "BUDGET_WARNING",
    }:
        return "WARNING"

    if normalized in {
        "EXCEEDED",
        "LIMIT_EXCEEDED",
        "BUDGET_EXCEEDED",
    }:
        return "EXCEEDED"

    return None


def upgrade() -> None:
    """Добавить месяц, нормализовать старые строки и создать ограничения."""

    with op.batch_alter_table(
        "notifications",
        schema=None,
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "month",
                sa.Date(),
                nullable=True,
            )
        )

    connection = op.get_bind()
    metadata = sa.MetaData()
    notifications = sa.Table(
        "notifications",
        metadata,
        autoload_with=connection,
    )

    # Новейшая строка сохраняется, более старые дубли удаляются.
    rows = (
        connection.execute(
            sa.select(
                notifications.c.id,
                notifications.c.user_id,
                notifications.c.type,
                notifications.c.created_at,
            ).order_by(
                notifications.c.created_at.desc(),
                notifications.c.id.desc(),
            )
        )
        .mappings()
        .all()
    )

    seen: set[tuple[str, object, str]] = set()

    for row in rows:
        notification_type = _normalized_type(
            row["type"],
        )

        # Неизвестный старый тип нельзя безопасно преобразовать.
        if notification_type is None:
            connection.execute(
                sa.delete(notifications).where(
                    notifications.c.id == row["id"],
                )
            )
            continue

        created_at = row["created_at"]

        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(
                created_at.replace(
                    "Z",
                    "+00:00",
                )
            )

        if not isinstance(created_at, datetime):
            raise RuntimeError("notifications.created_at содержит некорректное значение")

        month = created_at.date().replace(
            day=1,
        )
        deduplication_key = (
            str(row["user_id"]),
            month,
            notification_type,
        )

        if deduplication_key in seen:
            connection.execute(
                sa.delete(notifications).where(
                    notifications.c.id == row["id"],
                )
            )
            continue

        seen.add(deduplication_key)

        connection.execute(
            sa.update(notifications)
            .where(
                notifications.c.id == row["id"],
            )
            .values(
                month=month,
                type=notification_type,
            )
        )

    with op.batch_alter_table(
        "notifications",
        schema=None,
    ) as batch_op:
        batch_op.alter_column(
            "month",
            existing_type=sa.Date(),
            nullable=False,
        )
        batch_op.create_check_constraint(
            op.f("ck_notifications_notification_type"),
            "type IN ('WARNING', 'EXCEEDED')",
        )
        batch_op.create_unique_constraint(
            "uq_notifications_user_month_type",
            [
                "user_id",
                "month",
                "type",
            ],
        )


def downgrade() -> None:
    """Удалить ограничения и месяц уведомления."""

    with op.batch_alter_table(
        "notifications",
        schema=None,
    ) as batch_op:
        batch_op.drop_constraint(
            "uq_notifications_user_month_type",
            type_="unique",
        )
        batch_op.drop_constraint(
            op.f("ck_notifications_notification_type"),
            type_="check",
        )
        batch_op.drop_column(
            "month",
        )
