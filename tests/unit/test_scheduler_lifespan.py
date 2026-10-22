from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

import app.interface.api.app as app_module

pytestmark = pytest.mark.unit


class RecordingScheduler:
    """Тестовый планировщик: не создаёт поток и только записывает вызовы."""

    instances: ClassVar[list[RecordingScheduler]] = []

    def __init__(
        self,
        job: Callable[[], None],
        interval_seconds: int,
    ) -> None:
        self.job = job
        self.interval_seconds = interval_seconds
        self.started = False
        self.stopped = False
        self.instances.append(self)

    def start(self) -> None:
        self.started = True

    def shutdown(self) -> None:
        self.stopped = True


def test_scheduler_does_not_start_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    RecordingScheduler.instances.clear()

    monkeypatch.setattr(
        app_module,
        "get_settings",
        lambda: SimpleNamespace(
            scheduler_enabled=False,
            scheduler_interval_seconds=60,
        ),
    )
    monkeypatch.setattr(
        app_module,
        "OperationScheduler",
        RecordingScheduler,
    )

    application = app_module.create_app()

    with TestClient(application):
        assert application.state.operation_scheduler is None
        assert RecordingScheduler.instances == []


def test_scheduler_starts_and_stops_with_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    RecordingScheduler.instances.clear()

    monkeypatch.setattr(
        app_module,
        "get_settings",
        lambda: SimpleNamespace(
            scheduler_enabled=True,
            scheduler_interval_seconds=30,
        ),
    )
    monkeypatch.setattr(
        app_module,
        "OperationScheduler",
        RecordingScheduler,
    )

    application = app_module.create_app()

    with TestClient(application):
        assert len(RecordingScheduler.instances) == 1

        scheduler = RecordingScheduler.instances[0]

        assert application.state.operation_scheduler is scheduler
        assert scheduler.interval_seconds == 30
        assert scheduler.started is True
        assert scheduler.stopped is False

    assert scheduler.stopped is True
