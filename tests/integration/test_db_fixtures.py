"""Каркас тестов: изоляция БД, фабрики и клиенты (docs/06 §Фикстуры)."""

from datetime import UTC, date, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import FrozenClock
from app.core.persistence import Base
from tests.conftest import (
    CategoryFactory,
    LimitFactory,
    LoggedInClient,
    OperationFactory,
    RuleFactory,
    UserFactory,
)


async def test_db_session_schema_comes_from_migrations(
    db_session: async_sessionmaker[AsyncSession],
) -> None:
    """FR-1: схема тестовой БД - результат `alembic upgrade head`, не create_all."""
    async with db_session() as session:
        result = await session.execute(
            text("SELECT name FROM sqlite_master WHERE type = 'table'")
        )
        names = {row[0] for row in result}

    assert "alembic_version" in names
    assert set(Base.metadata.tables) <= names


async def test_clean_db_builds_schema_from_metadata(
    clean_db: async_sessionmaker[AsyncSession],
) -> None:
    """S1.4: create_all из моделей даёт полный набор таблиц - без alembic_version."""
    async with clean_db() as session:
        result = await session.execute(
            text("SELECT name FROM sqlite_master WHERE type = 'table'")
        )
        names = {row[0] for row in result}

    assert set(Base.metadata.tables) <= names
    assert "alembic_version" not in names


async def test_user_factory_caches_by_email(user_factory: UserFactory) -> None:
    """Повторный email (в любом регистре) возвращает ту же пару (user, token)."""
    first_user, first_token = await user_factory("alice@test.io")
    second_user, second_token = await user_factory("ALICE@test.io")

    assert first_user.id == second_user.id
    assert first_token == second_token


async def test_user_factory_generates_unique_emails(user_factory: UserFactory) -> None:
    first, _ = await user_factory()
    second, _ = await user_factory()

    assert first.email != second.email


async def test_factories_objects_belong_to_their_user(
    user_factory: UserFactory,
    category_factory: CategoryFactory,
    operation_factory: OperationFactory,
    limit_factory: LimitFactory,
    rule_factory: RuleFactory,
) -> None:
    """Каждый объект фабрик привязан к своему пользователю: изоляция видна глазом."""
    alice, _ = await user_factory("alice@test.io")
    bob, _ = await user_factory("bob@test.io")

    category = await category_factory(alice)
    operation = await operation_factory(alice, category=category)
    limit = await limit_factory(alice, category=category)
    rule = await rule_factory(alice, category=category)

    assert {category.user_id, operation.user_id, limit.user_id, rule.user_id} == {alice.id}
    assert alice.id != bob.id


async def test_rule_factory_next_run_follows_start_date(
    user_factory: UserFactory,
    rule_factory: RuleFactory,
) -> None:
    """next_run_at выводится из start_date: правило не просрочено до своего старта."""
    alice, _ = await user_factory("alice@test.io")
    rule = await rule_factory(alice, start_date=date(2026, 12, 1))

    assert rule.next_run_at == datetime(2026, 12, 1, tzinfo=UTC)


async def test_api_clients_are_two_different_users(
    api_client_a: LoggedInClient,
    api_client_b: LoggedInClient,
) -> None:
    """api_client_a и api_client_b - два залогиненных пользователя (docs/06 §Фикстуры)."""
    me_a = (await api_client_a.client.get("/api/v1/auth/me")).json()
    me_b = (await api_client_b.client.get("/api/v1/auth/me")).json()

    assert me_a["email"] == "alice@test.io"
    assert me_b["email"] == "bob@test.io"
    assert me_a["id"] != me_b["id"]


def test_frozen_clock_fixture_pins_the_date(frozen_clock: FrozenClock) -> None:
    """frozen_clock фиксирует 2026-10-15 независимо от реального времени."""
    assert frozen_clock.today() == date(2026, 10, 15)
