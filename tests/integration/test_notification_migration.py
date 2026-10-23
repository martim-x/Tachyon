"""Обновление старых уведомлений миграцией EP-17."""

import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_notification_migration_normalizes_and_deduplicates(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy-notifications.db"

    config = AlembicConfig(
        str(REPO_ROOT / "alembic.ini"),
    )
    config.set_main_option(
        "script_location",
        str(REPO_ROOT / "migrations"),
    )
    config.set_main_option(
        "sqlalchemy.url",
        f"sqlite+aiosqlite:///{database_path.as_posix()}",
    )

    command.upgrade(
        config,
        "dc3b03584f96",
    )

    user_id = uuid4().hex

    with sqlite3.connect(database_path) as connection:
        connection.executemany(
            """
            INSERT INTO notifications (
                id,
                user_id,
                type,
                payload,
                is_read,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    uuid4().hex,
                    user_id,
                    "limit_exceeded",
                    "{}",
                    0,
                    "2026-10-10 12:00:00",
                ),
                (
                    uuid4().hex,
                    user_id,
                    "EXCEEDED",
                    "{}",
                    0,
                    "2026-10-15 12:00:00",
                ),
                (
                    uuid4().hex,
                    user_id,
                    "unknown_legacy_type",
                    "{}",
                    0,
                    "2026-10-20 12:00:00",
                ),
            ],
        )

    command.upgrade(
        config,
        "head",
    )

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT month, type
            FROM notifications
            ORDER BY type
            """
        ).fetchall()

        assert rows == [
            (
                "2026-10-01",
                "EXCEEDED",
            )
        ]

        with pytest.raises(
            sqlite3.IntegrityError,
        ):
            connection.execute(
                """
                INSERT INTO notifications (
                    id,
                    user_id,
                    month,
                    type,
                    payload,
                    is_read,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid4().hex,
                    user_id,
                    "2026-10-01",
                    "EXCEEDED",
                    "{}",
                    0,
                    "2026-10-21 12:00:00",
                ),
            )
