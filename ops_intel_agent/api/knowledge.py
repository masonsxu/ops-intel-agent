"""Knowledge base CRUD + the engineer deposition endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.deposition import DepositionService
from ..core.pipeline import KNOWLEDGE_NS
from ..models import ErrorKnowledgeBase
from ..schemas.knowledge import (
    KnowledgeCreate,
    KnowledgeDepositionRequest,
    KnowledgeRead,
)
from ..services.embeddings import get_embedding_service
from ..services.vectorstore import VectorRecord, get_vector_store
from .deps import db_session

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("", response_model=list[KnowledgeRead], summary="List knowledge entries")
async def list_knowledge(
    limit: int = 50, session: AsyncSession = Depends(db_session)
) -> list[KnowledgeRead]:
    res = await session.execute(
        select(ErrorKnowledgeBase)
        .where(ErrorKnowledgeBase.is_active.is_(True))
        .order_by(ErrorKnowledgeBase.occurrence_count.desc(), ErrorKnowledgeBase.created_at.desc())
        .limit(limit)
    )
    return [KnowledgeRead.from_orm(k) for k in res.scalars().all()]


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
