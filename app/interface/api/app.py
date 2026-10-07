import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logging import configure_logging

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    configure_logging()

    application = FastAPI(
        title="Tachyon",
        description="Многопользовательский трекер доходов и расходов",
        version="0.1.0",
    )

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
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Internal server error",
                    "detail": None,
                }
            },
        )

    return application
