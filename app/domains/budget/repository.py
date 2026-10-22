from app.core.persistence.scoped_repository import ScopedRepository
from app.domains.budget.models import BudgetLimit


class BudgetRepository(ScopedRepository[BudgetLimit]):
    model = BudgetLimit
