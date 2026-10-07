import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.persistence import Base


class RecurringRule(Base):
    __tablename__ = "recurring_rules"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('daily', 'weekly', 'monthly')",
            name="recurring_kind",
        ),
        CheckConstraint("amount_cents > 0", name="recurring_amount_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"),
        index=True,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id"),
    )
    kind: Mapped[str] = mapped_column(String(20))
    interval: Mapped[int] = mapped_column(default=1)
    amount_cents: Mapped[int]
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    start_date: Mapped[date]
    end_date: Mapped[date | None] = mapped_column(nullable=True)
    next_run_at: Mapped[datetime]
    last_run_at: Mapped[datetime | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)


class RecurringExecution(Base):
    __tablename__ = "recurring_executions"
    __table_args__ = (
        UniqueConstraint(
            "rule_id",
            "period_date",
            name="uq_recurring_executions_rule_period",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"),
        index=True,
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recurring_rules.id"),
        index=True,
    )
    period_date: Mapped[date]
    operation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("operations.id"),
        nullable=True,
    )
