"""Единая точка подключения API-роутеров."""

from fastapi import APIRouter

from app.domains.budget.api import router as budget_router
from app.domains.identity.api import router as identity_router
from app.domains.ledger.api import router as ledger_router
from app.domains.reporting.api import forecast_router as reporting_forecast_router
from app.domains.reporting.api import router as reporting_router
from app.domains.scheduling.api import router as scheduling_router

api_router = APIRouter()

api_router.include_router(budget_router)
api_router.include_router(identity_router)
api_router.include_router(ledger_router)
api_router.include_router(scheduling_router)
api_router.include_router(reporting_router)
api_router.include_router(reporting_forecast_router)
