import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Модели импортируются ради регистрации таблиц в metadata
import app.domains.budget.models  # noqa: F401
import app.domains.identity.models  # noqa: F401
import app.domains.ledger.models  # noqa: F401
import app.domains.notification.models  # noqa: F401
import app.domains.scheduling.models  # noqa: F401
from app.core.persistence import Base


@pytest.fixture
async def engine(tmp_path):
    database_path = tmp_path / "isolation.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session