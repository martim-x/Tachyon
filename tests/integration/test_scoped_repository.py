"""Контракт ScopedRepository: user_id только из контекста, подмена невозможна."""

import uuid

import pytest

from app.core.persistence.scoped_repository import ScopedRepository
from app.core.user_context import user_scope
from app.domains.identity.models import User
from app.domains.ledger.repository import CategoryRepository
from tests.integration import factories

pytestmark = pytest.mark.integration


class UserRepositoryAttempt(ScopedRepository[User]):
    model = User


def test_model_without_user_id_cannot_be_scoped(session) -> None:
    with pytest.raises(TypeError, match="user_id"):
        UserRepositoryAttempt(session)


async def test_create_stamps_user_id_from_context(session) -> None:
    alice = await factories.create_user(session, "alice@test.io")
    bob = await factories.create_user(session, "bob@test.io")

    with user_scope(bob.id):
        repo = CategoryRepository(session)
        category = await repo.create(name="Продукты", kind="income")
        assert category.user_id == bob.id

        with pytest.raises(TypeError):
            await repo.create(user_id=alice.id, name="Кофе", kind="expense")

        rows = await repo.list()
        assert len(rows) == 1
        assert rows[0].user_id == bob.id


async def test_update_and_delete_work_for_owner(session) -> None:
    alice = await factories.create_user(session, "alice@test.io")

    with user_scope(alice.id):
        repo = CategoryRepository(session)
        category = await repo.create(name="Продукты", kind="income")

        updated = await repo.update(category.id, name="Транспорт")
        assert updated.name == "Транспорт"

        deleted = await repo.delete(category.id)
        assert deleted.id == category.id
        assert await repo.list() == []


async def test_isolation_update_rejects_user_id_and_id_substitution(session) -> None:
    """Замечание ревью к EP-02: update не двигает запись между пользователями."""
    alice = await factories.create_user(session, "alice@test.io")
    bob = await factories.create_user(session, "bob@test.io")

    with user_scope(bob.id):
        repo = CategoryRepository(session)
        category = await repo.create(name="Продукты", kind="income")

        with pytest.raises(TypeError, match="нельзя менять"):
            await repo.update(category.id, user_id=alice.id)
        with pytest.raises(TypeError, match="нельзя менять"):
            await repo.update(category.id, id=uuid.uuid4())

        reloaded = await repo.get_by_id(category.id)
        assert reloaded is not None
        assert reloaded.user_id == bob.id
