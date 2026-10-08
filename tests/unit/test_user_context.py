"""UserContext - единственный источник текущего пользователя (docs/02 механизм 2)."""

import uuid

import pytest

from app.core.errors import PermissionDenied
from app.core.user_context import get_current_user, reset_current_user, set_current_user, user_scope


def test_get_current_user_without_context_raises() -> None:
    with pytest.raises(PermissionDenied, match="контекст"):
        get_current_user()


def test_set_and_reset_roundtrip() -> None:
    user_id = uuid.uuid4()
    token = set_current_user(user_id)
    try:
        assert get_current_user() == user_id
    finally:
        reset_current_user(token)

    with pytest.raises(PermissionDenied):
        get_current_user()


def test_user_scope_nesting_and_cleanup() -> None:
    outer = uuid.uuid4()
    inner = uuid.uuid4()

    with user_scope(outer):
        assert get_current_user() == outer
        with user_scope(inner):
            assert get_current_user() == inner
        assert get_current_user() == outer

    with pytest.raises(PermissionDenied):
        get_current_user()