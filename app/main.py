"""FastAPI application entrypoint.

Owner: Carter (SWE).

Run locally:
    uvicorn app.main:app --reload

In Docker the same command runs as a non-root user (see Dockerfile).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api.routes import cards, health
from app.core.config import get_settings
from app.db.session import engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown lifecycle.

    Schema creation is handled by Alembic migrations (not create_all) so
    the DB stays reproducible across environments. On shutdown we dispose
    the connection pool cleanly.
    """
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
        # Don't leak interactive docs outside local/staging.
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.environment != "production" else None,
    )

    # --- Routers ---
    app.include_router(health.router)
    app.include_router(cards.router, prefix=settings.api_v1_prefix)
    # Future (Carter):    app.include_router(predict.router, prefix=settings.api_v1_prefix)
    # Future (Security):  app.include_router(auth.router,    prefix=settings.api_v1_prefix)

    return app


app = create_app()
