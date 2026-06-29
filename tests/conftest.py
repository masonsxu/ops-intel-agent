"""Shared test fixtures. All tests run fully offline with full isolation."""

from __future__ import annotations

import os

import pytest
import pytest_asyncio

# Force offline backends before any app imports.
os.environ.setdefault("OIA_EMBEDDING_PROVIDER", "local")
os.environ.setdefault("OIA_LLM_PROVIDER", "local")
os.environ.setdefault("OIA_VECTOR_STORE", "memory")
os.environ.setdefault("OIA_NOTIFIER_PROVIDER", "console")
os.environ["OIA_LOG_LEVEL"] = "WARNING"

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ops_intel_agent.config import get_settings
from ops_intel_agent.db.base import Base


def _reset_singletons() -> None:
    """Clear every lru_cached/cached service singleton so env changes apply."""
    get_settings.cache_clear()
    import ops_intel_agent.services.vectorstore.base as vsb

    vsb._store = None
    import ops_intel_agent.services.embeddings.base as eb

    eb._provider = None
    import ops_intel_agent.services.llm.base as lb

    lb._provider = None
    import ops_intel_agent.services.notifier.base as nb

    nb._notifier = None
    import ops_intel_agent.services.actions.registry as ar

    ar._registry = None


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Each test gets fresh singletons + a private vector-store path."""
    monkeypatch.setenv("OIA_MEMORY_VECTOR_PATH", str(tmp_path / "vectors.json"))
    _reset_singletons()
    yield
    _reset_singletons()


@pytest_asyncio.fixture
async def db_session():
    """Fresh in-memory SQLite database per test (isolated, no file leakage)."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()
