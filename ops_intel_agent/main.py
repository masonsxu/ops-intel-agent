"""FastAPI application factory and lifespan wiring."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import actions, alerts, health, knowledge
from .config import get_settings
from .db.session import dispose_engine, init_db
from .logging import configure_logging, get_logger


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging()
    log = get_logger("startup")
    log.info(
        "startup",
        environment=settings.environment,
        embedding=settings.embedding_provider,
        llm=settings.llm_provider,
        vector_store=settings.vector_store,
        notifier=settings.notifier_provider,
    )
    await init_db()
    flusher_task = None
    if settings.enable_aggregation:
        from .core.aggregator import AlertAggregator

        aggregator = AlertAggregator(
            window_seconds=settings.aggregation_window_seconds,
            min_cluster_size=settings.aggregation_min_cluster_size,
        )
        flusher_task = aggregator.start_flusher(interval=30.0)
        app.state.aggregator = aggregator
    try:
        yield
    finally:
        if flusher_task is not None:
            flusher_task.cancel()
        await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Ops Intel Agent",
        description=(
            "RAG + LLM agent that triages server anomalies: translates them "
            "into plain language for users and concrete playbooks for SREs, "
            "and deposits resolved incidents back into a vector knowledge base."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(alerts.router)
    app.include_router(knowledge.router)
    app.include_router(actions.router)
    return app


app = create_app()
