import pytest

from app.core.errors import AuthenticationFailed, Conflict
from app.domains.identity.repository import UserRepository
from app.domains.identity.service import IdentityService, verify_password

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_register_hashes_password(session) -> None:
    service = IdentityService(UserRepository(session))

    user = await service.register(
        email="User@Example.com",
        password="password123",
    )

    assert user.email == "user@example.com"
    assert user.password_hash != "password123"
    assert verify_password("password123", user.password_hash)


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(session) -> None:
    service = IdentityService(UserRepository(session))
    await service.register(email="user@example.com", password="password123")

    with pytest.raises(Conflict):
        await service.register(email="USER@example.com", password="another-password")


@pytest.mark.asyncio
async def test_authenticate_accepts_correct_password(session) -> None:
    service = IdentityService(UserRepository(session))
    registered = await service.register(
        email="user@example.com",
        password="password123",
    )

    authenticated = await service.authenticate(
        email="user@example.com",
        password="password123",
    )

    assert authenticated.id == registered.id


@pytest.mark.asyncio
async def test_authenticate_rejects_wrong_credentials(session) -> None:
    service = IdentityService(UserRepository(session))
    await service.register(email="user@example.com", password="password123")

    with pytest.raises(AuthenticationFailed):
        await service.authenticate(
            email="user@example.com",
            password="wrong-password",
        )

    with pytest.raises(AuthenticationFailed):
        await service.authenticate(
            email="missing@example.com",
            password="wrong-password",
        )
