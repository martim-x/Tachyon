"""Идемпотентность демо-данных (TT-36, FR-3).

Проверка /health без токена — tests/integration/test_health.py (FR-1).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def _run_seed(
    root: Path,
    db_file: Path,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{db_file}",
        "APP_ENV": "test",
        "PYTHONIOENCODING": "utf-8",
    }
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "scripts.seed"],
        check=True,
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_seed_is_idempotent(tmp_path: Path) -> None:
    """Повторный запуск seed не создаёт дублей (FR-3)."""

    db_file = tmp_path / "seed.db"
    root = Path(__file__).resolve().parents[2]

    # Миграции на временную БД.
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        cwd=str(root),
        env={
            **os.environ,
            "DATABASE_URL": f"sqlite+aiosqlite:///{db_file}",
            "PYTHONIOENCODING": "utf-8",
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    first = _run_seed(root, db_file)
    assert "Создан пользователь" in first.stdout

    second = _run_seed(root, db_file)
    assert "уже есть" in second.stdout
    assert "Создан пользователь" not in second.stdout

    # Проверка на уровне данных: ровно два демо-пользователя.
    check = subprocess.run(
        [
            sys.executable,
            "-c",
            "import asyncio, os\n"
            "from sqlalchemy import select, func\n"
            "from app.core.persistence import session_scope\n"
            "from app.domains.identity.models import User\n"
            "async def main():\n"
            "    async with session_scope() as s:\n"
            "        q = select(func.count()).select_from(User)\n"
            "        q = q.where(User.email.like('demo%@tachyon.local'))\n"
            "        n = (await s.execute(q)).scalar_one()\n"
            "        print(n)\n"
            "asyncio.run(main())\n",
        ],
        cwd=str(root),
        env={
            **os.environ,
            "DATABASE_URL": f"sqlite+aiosqlite:///{db_file}",
            "PYTHONIOENCODING": "utf-8",
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert check.returncode == 0, check.stderr
    assert check.stdout.strip() == "2"