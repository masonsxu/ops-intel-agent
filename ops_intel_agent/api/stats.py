"""Aggregate statistics for the dashboard."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.pipeline import KNOWLEDGE_NS
from ..models import ErrorAlert, ErrorKnowledgeBase
from ..services.vectorstore import get_vector_store
from .deps import db_session

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("", summary="Roll-up counts for the overview dashboard")
async def stats(session: AsyncSession = Depends(db_session)) -> dict:
    async def _count(stmt) -> int:
        res = await session.execute(stmt)
        return int(res.scalar() or 0)

    total = await _count(select(func.count(ErrorAlert.id)))
    open_ = await _count(select(func.count(ErrorAlert.id)).where(ErrorAlert.status == "open"))
    resolved = await _count(
        select(func.count(ErrorAlert.id)).where(ErrorAlert.status == "resolved")
    )
    matched = await _count(
        select(func.count(ErrorAlert.id)).where(ErrorAlert.match_status == "matched")
    )
    new_incident = await _count(
        select(func.count(ErrorAlert.id)).where(ErrorAlert.match_status == "new_incident")
    )
    knowledge_total = await _count(select(func.count(ErrorKnowledgeBase.id)))
    knowledge_active = await _count(
        select(func.count(ErrorKnowledgeBase.id)).where(ErrorKnowledgeBase.is_active.is_(True))
    )

    vector_count = 0
    try:
        vector_count = await get_vector_store().count(KNOWLEDGE_NS)
    except Exception:  # noqa: BLE001 - dashboard must not crash if the store hiccups
        vector_count = 0

    return {
        "alerts": {
            "total": total,
            "open": open_,
            "resolved": resolved,
            "matched": matched,
            "new_incident": new_incident,
        },
        "knowledge": {
            "total": knowledge_total,
            "active": knowledge_active,
            "vectors": vector_count,
        },
    }
