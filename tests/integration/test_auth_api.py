"""API аутентификации: регистрация, логин, 401 без токена (docs/03 §S2)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.domains.identity.service import create_access_token
from tests.conftest import ApiClientFactory

pytestmark = pytest.mark.integration


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


async def test_register_returns_user_without_password(api_client: ApiClientFactory) -> None:
    body = await register_user(api_client())

    assert set(body) == {"id", "email"}
    assert body["email"] == "user@example.com"


async def test_register_duplicate_email_returns_409(api_client: ApiClientFactory) -> None:
    client = api_client()
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


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("not-an-email", "password123"),
        ("user@example.com", "short"),
    ],
)
async def test_register_invalid_data_returns_422(
    api_client: ApiClientFactory,
    email: str,
    password: str,
) -> None:
    response = await api_client().post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )

    assert response.status_code == 422


async def test_login_and_me(api_client: ApiClientFactory) -> None:
    client = api_client()
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


async def test_login_with_wrong_credentials_returns_401(
    api_client: ApiClientFactory,
) -> None:
    client = api_client()
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


async def test_me_without_token_returns_401(api_client: ApiClientFactory) -> None:
    response = await api_client().get("/api/v1/auth/me")

    assert response.status_code == 401


async def test_me_rejects_invalid_tokens(api_client: ApiClientFactory) -> None:
    client = api_client()
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
