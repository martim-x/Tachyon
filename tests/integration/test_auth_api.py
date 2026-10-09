from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.persistence import Base, get_session, session_scope
from app.domains.identity.service import create_access_token
from app.interface.api.app import create_app


@pytest.fixture
async def client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    database_path = tmp_path / "auth.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path.as_posix()}",
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_scope(factory) as session:
            yield session

    application = create_app()
    application.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=application)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as test_client:
        yield test_client

    await engine.dispose()


async def register_user(client: AsyncClient) -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "user@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_register_returns_user_without_password(client: AsyncClient) -> None:
    body = await register_user(client)

    assert set(body) == {"id", "email"}
    assert body["email"] == "user@example.com"


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(client: AsyncClient) -> None:
    await register_user(client)

    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "USER@example.com",
            "password": "another-password",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("not-an-email", "password123"),
        ("user@example.com", "short"),
    ],
)
async def test_register_invalid_data_returns_422(
    client: AsyncClient,
    email: str,
    password: str,
) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_and_me(client: AsyncClient) -> None:
    registered = await register_user(client)

    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "user@example.com",
            "password": "password123",
        },
    )

    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    assert login_response.json()["token_type"] == "bearer"

    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.secret_key,
        algorithms=["HS256"],
    )
    assert payload["exp"] - payload["iat"] == settings.token_ttl * 60

    me_response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert me_response.status_code == 200
    assert me_response.json() == {
        "id": registered["id"],
        "email": registered["email"],
    }


@pytest.mark.asyncio
async def test_login_with_wrong_credentials_returns_401(
    client: AsyncClient,
) -> None:
    await register_user(client)

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "user@example.com",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_me_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_rejects_invalid_tokens(client: AsyncClient) -> None:
    expired_token = create_access_token(
        uuid4(),
        now=datetime.now(UTC) - timedelta(minutes=61),
        ttl_minutes=60,
    )
    foreign_token = create_access_token(
        uuid4(),
        secret_key="x" * 32,
    )
    missing_user_token = create_access_token(UUID(int=0))

    for token in (expired_token, foreign_token, missing_user_token):
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"
