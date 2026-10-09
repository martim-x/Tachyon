from uuid import uuid4

import pytest

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
