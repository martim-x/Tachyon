from uuid import uuid4

import pytest

from app.core.errors import Conflict
from app.domains.identity.repository import UserRepository


@pytest.mark.asyncio
async def test_user_repository_creates_and_finds_user(session) -> None:
    repository = UserRepository(session)

    user = await repository.create(
        email="User@Example.com",
        password_hash="test-hash",
    )

    assert user.id is not None
    assert user.email == "user@example.com"
    assert await repository.get_by_email("USER@EXAMPLE.COM") == user
    assert await repository.get_by_id(user.id) == user


@pytest.mark.asyncio
async def test_user_repository_returns_none_for_unknown_user(session) -> None:
    repository = UserRepository(session)

    assert await repository.get_by_email("missing@example.com") is None
    assert await repository.get_by_id(uuid4()) is None


@pytest.mark.asyncio
async def test_user_repository_maps_duplicate_email_to_conflict(session) -> None:
    repository = UserRepository(session)

    await repository.create(
        email="user@example.com",
        password_hash="first-hash",
    )
    await session.commit()

    with pytest.raises(Conflict):
        await repository.create(
            email="user@example.com",
            password_hash="second-hash",
        )

    assert await repository.get_by_email("user@example.com") is not None
