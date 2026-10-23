"""Add notification deduplication.

Revision ID: 515e2ddc9426
Revises: dc3b03584f96
Create Date: 2026-10-23 16:41:34.447873
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "515e2ddc9426"
down_revision: str | Sequence[str] | None = "dc3b03584f96"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Добавить месяц и ограничения дедупликации."""

    # Сначала nullable=True, чтобы миграция работала при наличии старых строк.
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

    # Старые уведомления привязываем к месяцу их создания.
    op.execute(
        sa.text(
            """
            UPDATE notifications
            SET month = date(created_at, 'start of month')
            WHERE month IS NULL
            """
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
