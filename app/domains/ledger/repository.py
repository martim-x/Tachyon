from app.core.persistence.scoped_repository import ScopedRepository
from app.domains.ledger.models import Category, Operation


class CategoryRepository(ScopedRepository[Category]):
    model = Category


class OperationRepository(ScopedRepository[Operation]):
    model = Operation