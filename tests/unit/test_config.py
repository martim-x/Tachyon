import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_accept_valid_values() -> None:
    settings = Settings(
        database_url="sqlite+aiosqlite:///./test.db",
        secret_key="x" * 32,
        token_ttl=60,
        _env_file=None,
    )

    assert settings.database_url == "sqlite+aiosqlite:///./test.db"
    assert settings.token_ttl == 60


def test_settings_reject_short_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(
            database_url="sqlite+aiosqlite:///./test.db",
            secret_key="short",
            _env_file=None,
        )