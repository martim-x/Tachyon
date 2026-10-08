from app.core.persistence.scoped_repository import ScopedRepository
from app.domains.scheduling.models import RecurringExecution, RecurringRule


class RecurringRuleRepository(ScopedRepository[RecurringRule]):
    model = RecurringRule


class RecurringExecutionRepository(ScopedRepository[RecurringExecution]):
    model = RecurringExecution