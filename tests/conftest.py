"""Единый conftest: все фикстуры проекта в одном месте (docs/06 §Фикстуры).

Правила каркаса:
- тесты не объявляют @pytest.fixture у себя - всё здесь;
- БД теста изолирована от рабочей: каждый тест получает копию шаблона,
  на который один раз за сессию накатан `alembic upgrade head`;
- фабрики принимают user= первым аргументом, чтобы изоляция была видна
  глазом в коде теста;
- api_client принимает токен явно; api_client_a/b - два залогиненных
  клиента разных пользователей.
"""

import shutil
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import NamedTuple, Protocol

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Модели импортируются ради регистрации таблиц в metadata
import app.domains.budget.models  # noqa: F401
import app.domains.identity.models  # noqa: F401
import app.domains.ledger.models  # noqa: F401
import app.domains.notification.models  # noqa: F401
import app.domains.scheduling.models  # noqa: F401
from app.core.clock import FrozenClock
from app.core.money import Money
from app.core.persistence import Base, get_session, session_scope
from app.domains.budget.models import BudgetLimit
from app.domains.identity.models import User
from app.domains.identity.service import create_access_token
from app.domains.ledger.models import Category, Operation
from app.domains.scheduling.models import RecurringRule
from app.interface.api.app import create_app
from tests.integration import factories

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_OPERATION_AMOUNT = Decimal("10.00")
DEFAULT_LIMIT_AMOUNT = Decimal("5000.00")
DEFAULT_RULE_AMOUNT = Decimal("1500.00")
DEFAULT_MONTH = date(2026, 10, 1)
FROZEN_TODAY = date(2026, 10, 15)


@pytest.fixture(scope="session")
def migrated_db_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Шаблон тестовой БД: один раз за сессию накатывается `alembic upgrade head`.

    Каждый тест получает копию этого файла, поэтому схема в тестах - ровно
    то, что alembic накатывает на рабочую БД, а не самодельный create_all.
    """
    db_path = tmp_path_factory.mktemp("templates") / "migrated.db"
    config = AlembicConfig(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    command.upgrade(config, "head")
    return db_path


@pytest.fixture
async def db_session(
    tmp_path: Path,
    migrated_db_template: Path,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Фабрика сессий изолированной БД: копия шаблона с миграциями на каждый тест.

    Изоляция от рабочей БД и от соседних тестов гарантирована файловой
    системой: тест пишет в свой файл и не может задеть чужие данные.
    Сессии открываются по месту: `async with db_session() as session:`.
    """
    db_path = tmp_path / "test.db"
    shutil.copyfile(migrated_db_template, db_path)
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
async def session(
    db_session: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """Открытая сессия для репозиторных тестов: одна транзакция на тест."""
    async with db_session() as session:
        yield session


@pytest.fixture
async def clean_db(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """БД, собранная из моделей: drop_all + create_all, без миграций.

    Нужна тестам самой схемы (S1.4): доказывает, что metadata даёт полный
    набор таблиц; основной db_session строится из миграций.
    """
    db_path = tmp_path / "clean.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


class UserFactory:
    """Создаёт пользователя; возвращает пару (user, token).

    Повторный вызов с тем же email возвращает закешированную пару, чтобы
    не плодить пользователей и не хешировать пароль повторно.
    """

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions
        self._cache: dict[str, tuple[User, str]] = {}
        self._counter = 0

    async def __call__(self, email: str | None = None) -> tuple[User, str]:
        if email is None:
            self._counter += 1
            email = f"user{self._counter}@test.io"
        key = email.lower()
        if key not in self._cache:
            async with self._sessions() as session:
                user = await factories.create_user(session, key)
                await session.commit()
            self._cache[key] = (user, create_access_token(user.id))
        return self._cache[key]


class CategoryFactory:
    """Категория пользователя; имя по умолчанию уникально в пределах теста."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions
        self._counter = 0

    async def __call__(
        self,
        user: User,
        name: str | None = None,
        kind: str = "expense",
    ) -> Category:
        if name is None:
            self._counter += 1
            name = f"Категория {self._counter}"
        async with self._sessions() as session:
            category = Category(user_id=user.id, name=name, kind=kind)
            session.add(category)
            await session.commit()
        return category


class OperationFactory:
    """Операция пользователя; сумма по умолчанию 10.00 (docs/06 §Фикстуры)."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        categories: CategoryFactory,
    ) -> None:
        self._sessions = sessions
        self._categories = categories

    async def __call__(
        self,
        user: User,
        amount: Decimal = DEFAULT_OPERATION_AMOUNT,
        *,
        category: Category | None = None,
        kind: str = "expense",
        occurred_at: datetime | None = None,
    ) -> Operation:
        if category is None:
            category = await self._categories(user)
        fields: dict[str, object] = {
            "user_id": user.id,
            "category_id": category.id,
            "amount_cents": Money(amount).to_cents(),
            "kind": kind,
        }
        if occurred_at is not None:
            fields["occurred_at"] = occurred_at
        async with self._sessions() as session:
            operation = Operation(**fields)
            session.add(operation)
            await session.commit()
        return operation


class LimitFactory:
    """Лимит бюджета пользователя; по умолчанию на октябрь 2026."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        categories: CategoryFactory,
    ) -> None:
        self._sessions = sessions
        self._categories = categories

    async def __call__(
        self,
        user: User,
        limit: Decimal = DEFAULT_LIMIT_AMOUNT,
        *,
        month: date | None = None,
        category: Category | None = None,
    ) -> BudgetLimit:
        if month is None:
            month = DEFAULT_MONTH
        if category is None:
            category = await self._categories(user)
        async with self._sessions() as session:
            row = BudgetLimit(
                user_id=user.id,
                category_id=category.id,
                month=month,
                limit_amount_cents=Money(limit).to_cents(),
            )
            session.add(row)
            await session.commit()
        return row


class RuleFactory:
    """Правило повторов пользователя; next_run_at выводится из start_date."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        categories: CategoryFactory,
    ) -> None:
        self._sessions = sessions
        self._categories = categories

    async def __call__(
        self,
        user: User,
        amount: Decimal = DEFAULT_RULE_AMOUNT,
        *,
        kind: str = "monthly",
        start_date: date | None = None,
        category: Category | None = None,
    ) -> RecurringRule:
        if start_date is None:
            start_date = DEFAULT_MONTH
        if category is None:
            category = await self._categories(user)
        async with self._sessions() as session:
            rule = RecurringRule(
                user_id=user.id,
                category_id=category.id,
                kind=kind,
                amount_cents=Money(amount).to_cents(),
                start_date=start_date,
                next_run_at=datetime(
                    start_date.year, start_date.month, start_date.day, tzinfo=UTC
                ),
            )
            session.add(rule)
            await session.commit()
        return rule


@pytest.fixture
def user_factory(db_session: async_sessionmaker[AsyncSession]) -> UserFactory:
    return UserFactory(db_session)


@pytest.fixture
def category_factory(db_session: async_sessionmaker[AsyncSession]) -> CategoryFactory:
    return CategoryFactory(db_session)


@pytest.fixture
def operation_factory(
    db_session: async_sessionmaker[AsyncSession],
    category_factory: CategoryFactory,
) -> OperationFactory:
    return OperationFactory(db_session, category_factory)


@pytest.fixture
def limit_factory(
    db_session: async_sessionmaker[AsyncSession],
    category_factory: CategoryFactory,
) -> LimitFactory:
    return LimitFactory(db_session, category_factory)


@pytest.fixture
def rule_factory(
    db_session: async_sessionmaker[AsyncSession],
    category_factory: CategoryFactory,
) -> RuleFactory:
    return RuleFactory(db_session, category_factory)


class ApiClientFactory(Protocol):
    """Фабрика httpx-клиентов: токен передаётся явно, без токена - аноним."""

    def __call__(self, token: str | None = None) -> AsyncClient: ...


@pytest.fixture
async def api_client(
    db_session: async_sessionmaker[AsyncSession],
) -> AsyncIterator[ApiClientFactory]:
    """httpx-клиент поверх ASGI-приложения с тестовой БД вместо рабочей."""
    application = create_app()

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_scope(db_session) as session:
            yield session

    application.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=application)
    created: list[AsyncClient] = []

    def make_client(token: str | None = None) -> AsyncClient:
        headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
        client = AsyncClient(transport=transport, base_url="http://test", headers=headers)
        created.append(client)
        return client

    yield make_client

    for client in created:
        await client.aclose()


class LoggedInClient(NamedTuple):
    """Залогиненный пользователь: объект, токен и клиент с этим токеном."""

    user: User
    token: str
    client: AsyncClient


@pytest.fixture
async def api_client_a(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
) -> LoggedInClient:
    """Клиент пользователя alice@test.io."""
    user, token = await user_factory("alice@test.io")
    return LoggedInClient(user, token, api_client(token))


@pytest.fixture
async def api_client_b(
    api_client: ApiClientFactory,
    user_factory: UserFactory,
) -> LoggedInClient:
    """Клиент пользователя bob@test.io."""
    user, token = await user_factory("bob@test.io")
    return LoggedInClient(user, token, api_client(token))


@pytest.fixture
def frozen_clock() -> FrozenClock:
    """Время тестов зафиксировано: 2026-10-15 (docs/06 §Фикстуры)."""
    return FrozenClock(FROZEN_TODAY)
