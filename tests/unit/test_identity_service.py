from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core.errors import AuthenticationFailed
from app.domains.identity.service import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

pytestmark = pytest.mark.unit


def test_hash_password_uses_random_salt() -> None:
    password = "strong-password"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != password
    assert first_hash != second_hash


def test_verify_password() -> None:
    password_hash = hash_password("correct-password")

    assert verify_password("correct-password", password_hash) is True
    assert verify_password("wrong-password", password_hash) is False


def test_verify_password_rejects_invalid_hash() -> None:
    assert verify_password("password", "not-a-bcrypt-hash") is False


def test_access_token_round_trip() -> None:
    user_id = uuid4()

    token = create_access_token(user_id)

    assert decode_access_token(token) == user_id


def test_expired_token_is_rejected() -> None:
    token = create_access_token(
        uuid4(),
        now=datetime.now(UTC) - timedelta(minutes=61),
        ttl_minutes=60,
    )

    with pytest.raises(AuthenticationFailed):
        decode_access_token(token)


def test_token_signed_with_another_secret_is_rejected() -> None:
    token = create_access_token(
        uuid4(),
        secret_key="a" * 32,
    )

    with pytest.raises(AuthenticationFailed):
        decode_access_token(token, secret_key="b" * 32)
