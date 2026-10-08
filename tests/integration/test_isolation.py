"""Матрица изоляции на репозиториях (docs/03 §S2.4, docs/06 «Матрица изоляции»)."""

import uuid
from datetime import date

import pytest
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError

from app.core.errors import NotFound, PermissionDenied
from app.core.persistence import Base
from app.core.user_context import user_scope
from app.domains.budget.repository import BudgetRepository
from app.domains.ledger.models import Operation
from app.domains.ledger.repository import CategoryRepository, OperationRepository
from app.domains.notification.repository import NotificationRepository
from app.domains.scheduling.repository import RecurringExecutionRepository, RecurringRuleRepository
from tests.integration import factories

CASES = [
    (CategoryRepository, "categories", factories.create_category, "name", "Транспорт"),
    (OperationRepository, "operations", factories.create_operation, "note", "взломано"),
    (BudgetRepository, "budget_limits", factories.create_budget_limit, "limit_amount_cents", 9999),
    (
        RecurringRuleRepository,
        "recurring_rules",
        factories.create_recurring_rule,
        "note",
        "взломано",
    ),
    (
        RecurringExecutionRepository,
        "recurring_executions",
        factories.create_recurring_execution,
        "period_date",
        date(2026, 11, 1),
    ),
    (NotificationRepository, "notifications", factories.create_notification, "is_read", True),
]


@pytest.mark.parametrize(
    ("repo_cls", "table", "seeder", "field", "value"),
    CASES,
    ids=[case[1] for case in CASES],
)
async def test_isolation_foreign_object_invisible_and_untouched(
    session, repo_cls, table, seeder, field, value
) -> None:
    alice = await factories.create_user(session, "alice@test.io")
    bob = await factories.create_user(session, "bob@test.io")
    alice_row = await seeder(session, alice.id)

    alice_repo = repo_cls(session)
    bob_repo = repo_cls(session)

    with user_scope(alice.id):
        rows = await alice_repo.list()
        assert len(rows) == 1
        assert rows[0].id == alice_row.id

    with user_scope(bob.id):
        assert await bob_repo.list() == []
        assert await bob_repo.get_by_id(alice_row.id) is None
        with pytest.raises(NotFound):
            await bob_repo.get_or_404(alice_row.id)
        with pytest.raises(NotFound):
            await bob_repo.update(alice_row.id, **{field: value})
        with pytest.raises(NotFound):
            await bob_repo.delete(alice_row.id)

    with user_scope(alice.id):
        row = await alice_repo.get_by_id(alice_row.id)
        assert row is not None
        assert getattr(row, field) != value


@pytest.mark.parametrize(
    "repo_cls", [case[0] for case in CASES], ids=[case[1] for case in CASES]
)
async def test_isolation_repository_without_context_raises(session, repo_cls) -> None:
    """Пустой контекст - это исключение, а не пустая выдача (docs/02 механизм 3)."""
    repo = repo_cls(session)
    pk = uuid.uuid4()

    with pytest.raises(PermissionDenied):
        await repo.list()
    with pytest.raises(PermissionDenied):
        await repo.get_by_id(pk)
    with pytest.raises(PermissionDenied):
        await repo.get_or_404(pk)
    with pytest.raises(PermissionDenied):
        await repo.create(name="x")
    with pytest.raises(PermissionDenied):
        await repo.update(pk, name="x")
    with pytest.raises(PermissionDenied):
        await repo.delete(pk)


async def test_isolation_same_category_name_for_different_users(session) -> None:
    """Имена категорий у пользователей независимы (docs/03 §S2.4, последний критерий)."""
    alice = await factories.create_user(session, "alice@test.io")
    bob = await factories.create_user(session, "bob@test.io")

    with user_scope(alice.id):
        alice_category = await CategoryRepository(session).create(name="Продукты", kind="income")
    with user_scope(bob.id):
        bob_category = await CategoryRepository(session).create(name="Продукты", kind="income")

    assert alice_category.user_id == alice.id
    assert bob_category.user_id == bob.id


async def test_isolation_same_category_name_for_same_user_rejected(session) -> None:
    alice = await factories.create_user(session, "alice@test.io")

    with user_scope(alice.id):
        repo = CategoryRepository(session)
        await repo.create(name="Продукты", kind="income")
        with pytest.raises(IntegrityError):
            await repo.create(name="Продукты", kind="income")
    await session.rollback()


async def test_isolation_insert_without_user_id_rejected(session) -> None:
    """Запись без user_id отвергается констрейнтом (docs/03 §S2.4, критерий 4)."""
    alice = await factories.create_user(session, "alice@test.io")
    category = await factories.create_category(session, alice.id)

    with pytest.raises(IntegrityError):
        await session.execute(
            insert(Operation).values(
                category_id=category.id,
                amount_cents=100,
                kind="expense",
            )
        )
    await session.rollback()


def test_isolation_user_id_constraints_in_every_domain_table() -> None:
    """Аудит констрейнтов: user_id NOT NULL, с индексом и FK на users в каждой таблице."""
    expected = {
        "categories",
        "operations",
        "budget_limits",
        "notifications",
        "recurring_rules",
        "recurring_executions",
    }
    tables = {
        name: table for name, table in Base.metadata.tables.items() if name != "users"
    }
    assert set(tables) == expected

    for name, table in tables.items():
        column = table.columns["user_id"]
        assert not column.nullable, name
        assert column.index, name
        (fk,) = column.foreign_keys
        assert fk.target_fullname == "users.id", name