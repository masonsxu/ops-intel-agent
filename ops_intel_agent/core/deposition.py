"""Knowledge closed-loop: turn a resolved incident into reusable knowledge.

Flow:
  1. Engineer resolves a "new_incident" alert and leaves free-form notes.
  2. We feed (notes + original log) to the LLM, which emits structured fields.
  3. We create a knowledge base row + its embedding in the vector store.
  4. Next time the same error fires, retrieval matches instantly.

This is the mechanism by which the system "gets smarter over time" with no
curator in the loop.
"""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING

from sqlalchemy import select

from ..logging import get_logger
from ..models import ErrorAlert, ErrorKnowledgeBase
from ..schemas.knowledge import KnowledgeDepositionRequest
from ..services.embeddings import get_embedding_service
from ..services.llm import get_llm_service
from ..services.vectorstore import VectorRecord, get_vector_store
from .pipeline import KNOWLEDGE_NS

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)


class DepositionService:
    def __init__(self) -> None:
        self.llm = get_llm_service()
        self.embeddings = get_embedding_service()
        self.store = get_vector_store()

    async def deposit(
        self, session: AsyncSession, req: KnowledgeDepositionRequest
    ) -> ErrorKnowledgeBase:
        alert = await session.get(ErrorAlert, req.alert_id)
        if alert is None:
            raise ValueError(f"alert {req.alert_id} not found")
        raw_log = alert.raw_log

        structured = await self.llm.build_knowledge(req, raw_log)
        title = structured.get("title") or f"{req.error_type or '故障'} - {req.root_cause[:60]}"

        kb = ErrorKnowledgeBase(
            # An engineer-supplied classification is authoritative; fall back
            # to the LLM's normalized classification.
            error_type=req.error_type or structured.get("error_type"),
            title=title,
            raw_log_sample=raw_log,
            root_cause=structured.get("root_cause") or req.root_cause,
            user_guide=structured.get("user_guide") or "请联系值班工程师确认影响范围。",
            engineer_guide=structured.get("engineer_guide") or req.resolution,
            source=f"engineer:{req.engineer}",
            tags=",".join(req.tags) if req.tags else None,
            confidence=1.0,
        )
        session.add(kb)
        await session.flush()

        vec = await self.embeddings.embed(_canonical(raw_log))
        await self.store.upsert(
            VectorRecord(
                namespace=KNOWLEDGE_NS,
                id=kb.id,
                text=raw_log,
                embedding=vec,
            )
        )

        # Link the originating alert back to the new knowledge.
        alert.matched_knowledge_id = kb.id
        alert.match_status = "deposited"
        alert.status = "resolved"
        from datetime import datetime

        alert.resolved_at = datetime.now(UTC)

        await session.commit()
        log.info(
            "deposition.created",
            knowledge_id=kb.id,
            alert_id=alert.id,
            error_type=kb.error_type,
        )
        return kb

    async def list_recent(self, session: AsyncSession, limit: int = 20) -> list[ErrorKnowledgeBase]:
        res = await session.execute(
            select(ErrorKnowledgeBase)
            .where(ErrorKnowledgeBase.is_active.is_(True))
            .order_by(ErrorKnowledgeBase.created_at.desc())
            .limit(limit)
        )
        return list(res.scalars().all())


def _canonical(raw: str) -> str:
    from ..extractors import parse_log

    return parse_log(raw).canonical_text
