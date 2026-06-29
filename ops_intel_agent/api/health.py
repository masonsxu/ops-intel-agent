"""Health & readiness probes."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["meta"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/ready")
async def ready() -> dict:
    from ..config import get_settings
    from ..services.vectorstore import get_vector_store

    settings = get_settings()
    store = get_vector_store()
    count = await store.count("knowledge")
    return {
        "status": "ready",
        "embedding_provider": settings.embedding_provider,
        "llm_provider": settings.llm_provider,
        "vector_store": settings.vector_store,
        "notifier": settings.notifier_provider,
        "knowledge_vectors": count,
    }
