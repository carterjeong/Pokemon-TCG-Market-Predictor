"""Health-check routes.

Owner: Carter (SWE).

* GET /health      — liveness (no dependencies touched)
* GET /health/db   — readiness (executes SELECT 1 through the async session)
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app import __version__
from app.core.config import Settings, get_settings
from app.db.session import SessionDep
from app.schemas.health import DBHealthResponse, HealthResponse

router = APIRouter(tags=["health"])

SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/health", response_model=HealthResponse)
async def health(settings: SettingsDep) -> HealthResponse:
    """Liveness probe — process is up and serving requests."""
    return HealthResponse(
        app=settings.app_name,
        environment=settings.environment,
        version=__version__,
    )


@router.get("/health/db", response_model=DBHealthResponse)
async def health_db(session: SessionDep) -> DBHealthResponse:
    """Readiness probe — verifies PostgreSQL connectivity (async)."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        return DBHealthResponse(status="degraded", database="unreachable")
    return DBHealthResponse(status="ok", database="reachable")
