import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.persistence import Base


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (Index("ix_categories_user_name", "user_id", "name", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(50))
    kind: Mapped[str] = mapped_column(String(20))
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_default: Mapped[bool] = mapped_column(default=False)


class Operation(Base):
    __tablename__ = "operations"
    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="amount_positive"),
        CheckConstraint(
            "kind IN ('income', 'expense')",
            name="operation_kind",
        ),
        Index("ix_operations_user_occurred", "user_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"),
        index=True,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id"),
    )
    amount_cents: Mapped[int]
    kind: Mapped[str] = mapped_column(String(20))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="manual")
    recurring_execution_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
