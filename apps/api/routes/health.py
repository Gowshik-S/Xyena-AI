from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import text

from packages.config import Settings, get_settings
from packages.contracts.common import HealthStatus
from packages.persistence import get_database

router = APIRouter(tags=["Health"])


@router.get("/health/live", operation_id="health_liveness", response_model=HealthStatus)
async def liveness(settings: Settings = Depends(get_settings)) -> HealthStatus:
    return HealthStatus(
        status="ok",
        service="xyena-api",
        version="0.1.0",
        checked_at=datetime.now(UTC),
    )


@router.get("/health/ready", operation_id="health_readiness", response_model=HealthStatus)
async def readiness(settings: Settings = Depends(get_settings)) -> HealthStatus:
    database = get_database()
    async with database.session(service_role="health") as db:
        await db.execute(text("SELECT 1"))
    return HealthStatus(
        status="ready",
        service="xyena-api",
        version="0.1.0",
        checked_at=datetime.now(UTC),
    )

