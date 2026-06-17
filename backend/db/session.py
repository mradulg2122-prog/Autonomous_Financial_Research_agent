"""
ARA-1 Database Session Helper
Provides get_db_session as an async context manager for background tasks
that cannot use FastAPI's Depends() injection.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import async_session_factory


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for database sessions used in background tasks.
    Usage:
        async with get_db_session() as db:
            db.add(obj)
            await db.commit()
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
