"""Async database engine, session factory, and FastAPI dependency.

Owner: Carter (SWE).

SQLAlchemy 2.0 asyncio pattern: one engine per process, an
`async_sessionmaker` factory, and a per-request session injected with
`Depends(get_db_session)` that commits on success and rolls back on error.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_settings = get_settings()

engine: AsyncEngine = create_async_engine(
    _settings.database_url,
    echo=_settings.debug,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

AsyncSessionFactory = async_sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped session; commit on success, rollback on error."""
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Annotated alias so routes can declare `session: SessionDep`.
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
