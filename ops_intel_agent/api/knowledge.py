"""Knowledge base CRUD + the engineer deposition endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.deposition import DepositionService
from ..core.pipeline import KNOWLEDGE_NS
from ..models import ErrorKnowledgeBase
from ..schemas.knowledge import (
    KnowledgeCreate,
    KnowledgeDepositionRequest,
    KnowledgeRead,
    KnowledgeSearchHit,
)
from ..services.embeddings import get_embedding_service
from ..services.vectorstore import VectorRecord, get_vector_store
from .deps import db_session

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("", response_model=list[KnowledgeRead], summary="List knowledge entries")
async def list_knowledge(
    limit: int = Query(50, ge=1, le=500),
    date: str | None = Query(None, description="Exact local date YYYY-MM-DD"),
    date_from: str | None = Query(None, description="Inclusive lower bound YYYY-MM-DD"),
    date_to: str | None = Query(None, description="Inclusive upper bound YYYY-MM-DD"),
    error_type: str | None = Query(None, description="Exact error type"),
    q: str | None = Query(None, description="Substring search on title / raw log / root cause"),
    session: AsyncSession = Depends(db_session),
) -> list[KnowledgeRead]:
    stmt = (
        select(ErrorKnowledgeBase)
        .where(ErrorKnowledgeBase.is_active.is_(True))
        .order_by(
            ErrorKnowledgeBase.occurrence_count.desc(),
            ErrorKnowledgeBase.created_at.desc(),
        )
        .limit(limit)
    )
    if date:
        stmt = stmt.where(func.date(ErrorKnowledgeBase.created_at) == date)
    if date_from:
        stmt = stmt.where(func.date(ErrorKnowledgeBase.created_at) >= date_from)
    if date_to:
        stmt = stmt.where(func.date(ErrorKnowledgeBase.created_at) <= date_to)
    if error_type:
        stmt = stmt.where(ErrorKnowledgeBase.error_type == error_type)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                ErrorKnowledgeBase.title.ilike(like),
                ErrorKnowledgeBase.raw_log_sample.ilike(like),
                ErrorKnowledgeBase.root_cause.ilike(like),
            )
        )
    res = await session.execute(stmt)
    return [KnowledgeRead.from_orm(k) for k in res.scalars().all()]


@router.get(
    "/search",
    response_model=list[KnowledgeSearchHit],
    summary="Semantic (vector) search over the knowledge base",
)
async def search_knowledge(
    q: str = Query(..., min_length=1, description="Free-text query"),
    k: int = Query(5, ge=1, le=50, description="Top-K results"),
    session: AsyncSession = Depends(db_session),
) -> list[KnowledgeSearchHit]:
    """Embed the query and return the top-K most similar knowledge entries.

    This is the "vector fuzzy search" path: it ranks by cosine similarity, so
    results match on *meaning* rather than exact keywords (e.g. a query about
    "db pool timeout" still surfaces a known MySQL HikariCP incident).
    """
    embeddings = get_embedding_service()
    store = get_vector_store()
    from ..extractors import parse_log

    query_vec = await embeddings.embed(parse_log(q).canonical_text)
    matches = await store.search(KNOWLEDGE_NS, query_vec, k=k)
    if not matches:
        return []
    by_id = {m.id: m.score for m in matches}
    rows = (
        (
            await session.execute(
                select(ErrorKnowledgeBase).where(
                    ErrorKnowledgeBase.id.in_(list(by_id)),
                    ErrorKnowledgeBase.is_active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    hits_map = {r.id: r for r in rows}
    # Preserve the vector ranking order (highest similarity first).
    out: list[KnowledgeSearchHit] = []
    for m in matches:
        kb = hits_map.get(m.id)
        if kb is None:
            continue
        out.append(
            KnowledgeSearchHit(**KnowledgeRead.from_orm(kb).model_dump(), similarity=m.score)
        )
    return out


@router.get("/{knowledge_id}", response_model=KnowledgeRead)
async def get_knowledge(
    knowledge_id: int, session: AsyncSession = Depends(db_session)
) -> KnowledgeRead:
    kb = await session.get(ErrorKnowledgeBase, knowledge_id)
    if kb is None:
        raise HTTPException(404, "knowledge not found")
    return KnowledgeRead.from_orm(kb)


@router.post(
    "",
    response_model=KnowledgeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Manually add a knowledge entry",
)
async def create_knowledge(
    payload: KnowledgeCreate, session: AsyncSession = Depends(db_session)
) -> KnowledgeRead:
    kb = ErrorKnowledgeBase(
        error_type=payload.error_type,
        title=payload.title,
        raw_log_sample=payload.raw_log_sample,
        root_cause=payload.root_cause,
        user_guide=payload.user_guide,
        engineer_guide=payload.engineer_guide,
        source=payload.source,
        tags=",".join(payload.tags) if payload.tags else None,
        confidence=1.0,
    )
    session.add(kb)
    await session.flush()
    embeddings = get_embedding_service()
    store = get_vector_store()
    from ..extractors import parse_log

    vec = await embeddings.embed(parse_log(payload.raw_log_sample).canonical_text)
    await store.upsert(
        VectorRecord(namespace=KNOWLEDGE_NS, id=kb.id, text=payload.raw_log_sample, embedding=vec)
    )
    await session.commit()
    await session.refresh(kb)
    return KnowledgeRead.from_orm(kb)


@router.post(
    "/depositions",
    response_model=KnowledgeRead,
    summary="Deposit an engineer's resolution as new knowledge",
)
async def deposit(
    req: KnowledgeDepositionRequest, session: AsyncSession = Depends(db_session)
) -> KnowledgeRead:
    try:
        kb = await DepositionService().deposit(session, req)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return KnowledgeRead.from_orm(kb)


@router.delete("/{knowledge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_knowledge(
    knowledge_id: int, session: AsyncSession = Depends(db_session)
) -> None:
    kb = await session.get(ErrorKnowledgeBase, knowledge_id)
    if kb is None:
        raise HTTPException(404, "knowledge not found")
    kb.is_active = False
    store = get_vector_store()
    await store.delete(KNOWLEDGE_NS, knowledge_id)
    await session.commit()
