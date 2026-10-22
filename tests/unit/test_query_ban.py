"""docs/02 «Механизм 6»: query-builder наружу не выдаётся - grep по ".query(" пуст."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

APP_ROOT = Path(__file__).resolve().parents[2] / "app"


def test_query_builder_not_used() -> None:
    offenders = [
        str(path.relative_to(APP_ROOT))
        for path in sorted(APP_ROOT.rglob("*.py"))
        if ".query(" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
