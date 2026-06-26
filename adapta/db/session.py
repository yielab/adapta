"""Async SQLAlchemy session factory.

``expire_on_commit=False`` is set on the session factory so that ORM objects
remain accessible after ``await db.commit()`` without triggering an implicit
SELECT.  The default (``expire_on_commit=True``) would expire every attribute
on commit, forcing a round-trip for any attribute read after the commit —
which breaks the common pattern of returning the just-committed object.

Commit-before-return rule: mutating request handlers must call
``await db.commit()`` explicitly *before* returning the response.  FastAPI's
``get_db`` dependency commits only after the response body is sent (ASGI
ordering), so an immediate follow-up request or a concurrently-scheduled
background task opened its own session would find uncommitted rows and either
see stale data or be stuck.  See MEMORY.md (commit-before-return-pattern).
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from adapta.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async DB session scoped to one request.

    Commits on clean exit, rolls back on exception.  Callers that need
    changes visible to concurrently-started background tasks must call
    ``await db.commit()`` explicitly before scheduling the task — this
    dependency's auto-commit runs after the response is sent, which is too late.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
