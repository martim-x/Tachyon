import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.persistence import session_scope


@pytest.mark.asyncio
async def test_parallel_requests_use_different_sessions(tmp_path) -> None:
    database_path = tmp_path / "sessions.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as first_session, factory() as second_session:
        assert first_session is not second_session

    await engine.dispose()


@pytest.mark.asyncio
async def test_exception_rolls_back_transaction(tmp_path) -> None:
    database_path = tmp_path / "rollback.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.execute(text("CREATE TABLE example (id INTEGER PRIMARY KEY)"))

    with pytest.raises(RuntimeError):
        async with session_scope(factory) as session:
            await session.execute(text("INSERT INTO example DEFAULT VALUES"))
            raise RuntimeError("force rollback")

    async with factory() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM example"))
        assert result.scalar_one() == 0

    await engine.dispose()
