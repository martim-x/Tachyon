import uuid
from datetime import date

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.persistence import Base


class BudgetLimit(Base):
    __tablename__ = "budget_limits"
    __table_args__ = (
        CheckConstraint("limit_amount_cents > 0", name="limit_positive"),
        UniqueConstraint(
            "user_id",
            "category_id",
            "month",
            name="uq_budget_limits_user_category_month",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"),
        index=True,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id"),
    )
    month: Mapped[date]
    limit_amount_cents: Mapped[int]
