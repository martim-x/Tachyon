import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logging import configure_logging
from app.domains.identity.api import router as identity_router
from app.domains.ledger.api import router as ledger_router
from app.interface.api.exception_handlers import (
    error_body,
    register_exception_handlers,
)

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    configure_logging()

    application = FastAPI(
        title="Tachyon",
        description="Многопользовательский трекер доходов и расходов",
        version="0.1.0",
    )
    register_exception_handlers(application)
    application.include_router(identity_router)
    application.include_router(ledger_router)

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
