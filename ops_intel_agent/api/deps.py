"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_db


async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async for s in get_db():
        yield s
