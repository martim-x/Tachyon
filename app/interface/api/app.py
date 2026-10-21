import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.clock import SystemClock
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.persistence.session import session_scope
from app.domains.identity.api import router as identity_router
from app.domains.ledger.api import router as ledger_router
from app.domains.scheduling.api import router as scheduling_router
from app.domains.scheduling.service import RecurringService
from app.infrastructure.scheduler import OperationScheduler
from app.interface.api.exception_handlers import (
    error_body,
    register_exception_handlers,
)

logger = logging.getLogger(__name__)


async def generate_due_operations_job() -> None:
    """Запустить генерацию на engine, принадлежащем текущему event loop.

    BackgroundScheduler запускает задачу в отдельном потоке, поэтому нельзя
    использовать глобальный async engine приложения: его соединения могут
    принадлежать другому event loop.
    """

    settings = get_settings()

    job_engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
    )
    job_session_factory = async_sessionmaker(
        bind=job_engine,
        expire_on_commit=False,
    )

    try:
        async with session_scope(job_session_factory) as session:
            service = RecurringService(session)
            await service.generate_due_operations(
                user_id=None,
                until=SystemClock().now(),
                continue_on_error=True,
            )
    finally:
        # Engine создаётся и уничтожается внутри одного event loop.
        await job_engine.dispose()


def run_generate_due_operations_job() -> None:
    """Синхронная точка входа для фонового потока APScheduler."""

    try:
        asyncio.run(generate_due_operations_job())
    except Exception:
        logger.exception("Scheduled recurring operation generation failed")


@asynccontextmanager
async def application_lifespan(
    application: FastAPI,
) -> AsyncIterator[None]:
    """Запустить планировщик вместе с приложением и остановить при shutdown."""

    settings = get_settings()
    scheduler: OperationScheduler | None = None

    if settings.scheduler_enabled:
        scheduler = OperationScheduler(
            job=run_generate_due_operations_job,
            interval_seconds=settings.scheduler_interval_seconds,
        )
        scheduler.start()

    # Сохраняем в state, чтобы состояние можно было проверить в тестах.
    application.state.operation_scheduler = scheduler

    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown()


def create_app() -> FastAPI:
    configure_logging()

    application = FastAPI(
        title="Tachyon",
        description="Многопользовательский трекер доходов и расходов",
        version="0.1.0",
        lifespan=application_lifespan,
    )

    register_exception_handlers(application)
    application.include_router(identity_router)
    application.include_router(ledger_router)
    application.include_router(scheduling_router)

    @application.get("/health", tags=["Система"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.exception_handler(Exception)
    async def handle_unexpected_error(
        _request: Request,
        error: Exception,
    ) -> JSONResponse:
        logger.exception("Unhandled application error: %s", error)
        return JSONResponse(
            error_body("INTERNAL_ERROR", "Internal server error"),
            status_code=500,
        )

    return application
