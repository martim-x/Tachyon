"""Read-only выборка данных для отчётов."""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, select

from app.core.persistence.scoped_repository import ScopedRepository
from app.domains.budget.models import BudgetLimit
from app.domains.ledger.models import Category, Operation
from app.domains.reporting.queries import ReportRow


def day_start(day: date) -> datetime:
    """Начало календарного дня в UTC."""

    return datetime(
        day.year,
        day.month,
        day.day,
        tzinfo=UTC,
    )


class ReportingRepository(ScopedRepository[Operation]):
    """Выборки отчётов, ограниченные текущим пользователем."""

    model = Operation

    async def period_rows(
        self,
        *,
        date_from: date,
        date_to: date,
        limit_month: date,
    ) -> list[ReportRow]:
        """Получить операции периода с категориями и лимитами.

        Пользовательский фильтр физически находится во вложенном запросе
        `_scoped()`, поэтому чужой user_id нельзя подставить через API.
        """

        scoped_query = self._scoped().where(
            Operation.occurred_at >= day_start(date_from),
        )

        # Обычный период фильтруется по исключающей верхней границе:
        # для 31 октября это будет начало 1 ноября.
        #
        # Для date.max нельзя прибавить один день — возникнет OverflowError.
        # Верхняя граница там не нужна: более позднего datetime не существует.
        if date_to < date.max:
            period_end = date_to + timedelta(days=1)
            scoped_query = scoped_query.where(
                Operation.occurred_at < day_start(period_end),
            )

        scoped_operations = scoped_query.subquery()

        statement = (
            select(
                scoped_operations.c.category_id,
                Category.name.label("category_name"),
                scoped_operations.c.kind,
                scoped_operations.c.amount_cents,
                BudgetLimit.limit_amount_cents.label("limit_cents"),
            )
            .select_from(scoped_operations)
            .outerjoin(
                Category,
                and_(
                    Category.id == scoped_operations.c.category_id,
                    Category.user_id == scoped_operations.c.user_id,
                ),
            )
            .outerjoin(
                BudgetLimit,
                and_(
                    BudgetLimit.category_id == scoped_operations.c.category_id,
                    BudgetLimit.user_id == scoped_operations.c.user_id,
                    BudgetLimit.month == limit_month,
                ),
            )
            .order_by(
                scoped_operations.c.occurred_at,
                scoped_operations.c.id,
            )
        )

        result = await self._session.execute(statement)

        return [
            ReportRow(
                category_id=row["category_id"],
                category_name=row["category_name"],
                kind=str(row["kind"]),
                amount_cents=int(row["amount_cents"]),
                limit_cents=(None if row["limit_cents"] is None else int(row["limit_cents"])),
            )
            for row in result.mappings().all()
        ]
