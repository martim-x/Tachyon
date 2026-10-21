"""Инфраструктурная обёртка APScheduler.

Это единственный модуль приложения, которому разрешено импортировать apscheduler.
Бизнес-логика генерации операций передаётся сюда как обычная функция.
"""

import logging
from collections.abc import Callable

from apscheduler.schedulers.background import (  # type: ignore[import-untyped]
    BackgroundScheduler,
)

logger = logging.getLogger(__name__)

SCHEDULER_JOB_ID = "generate-due-operations"


class OperationScheduler:
    """Запускает периодическую генерацию просроченных операций."""

    def __init__(
        self,
        job: Callable[[], None],
        interval_seconds: int,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("Интервал планировщика должен быть больше нуля")

        self._scheduler = BackgroundScheduler(timezone="UTC")
        self._scheduler.add_job(
            job,
            trigger="interval",
            seconds=interval_seconds,
            id=SCHEDULER_JOB_ID,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    @property
    def running(self) -> bool:
        """Показывает, запущен ли фоновый планировщик."""
        return bool(self._scheduler.running)

    def start(self) -> None:
        """Запустить планировщик, если он ещё не запущен."""
        if self.running:
            return

        self._scheduler.start()
        logger.info("Background scheduler started")

    def shutdown(self) -> None:
        """Остановить планировщик без ожидания выполняющихся задач."""
        if not self.running:
            return

        self._scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped")
