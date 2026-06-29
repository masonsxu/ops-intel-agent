"""Alert ingestion & query endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.pipeline import TriagePipeline
from ..logging import get_logger
from ..models import ErrorAlert
from ..schemas.alert import AlertCreate, AlertRead, AlertWithReport
from ..schemas.report import DiagnosticReport
from .deps import db_session

router = APIRouter(prefix="/alerts", tags=["alerts"])
log = get_logger(__name__)


@router.post(
    "",
    response_model=AlertWithReport,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest an anomaly alert and run triage",
)
async def ingest_alert(
    payload: AlertCreate,
    session: AsyncSession = Depends(db_session),
) -> AlertWithReport:
    pipeline = TriagePipeline()
    result = await pipeline.process(session, payload)
    await session.refresh(result.alert)
    return AlertWithReport(
        **AlertRead.model_validate(result.alert).model_dump(),
        report=result.report,
    )


@router.get("", response_model=list[AlertRead], summary="List recent alerts")
async def list_alerts(
    limit: int = 50,
    status_filter: str | None = None,
    session: AsyncSession = Depends(db_session),
) -> list[AlertRead]:
    q = select(ErrorAlert).order_by(ErrorAlert.created_at.desc()).limit(limit)
    if status_filter:
        q = q.where(ErrorAlert.status == status_filter)
    res = await session.execute(q)
    return [AlertRead.model_validate(a) for a in res.scalars().all()]


@router.get("/{alert_id}", response_model=AlertWithReport)
async def get_alert(alert_id: int, session: AsyncSession = Depends(db_session)) -> AlertWithReport:
    alert = await session.get(ErrorAlert, alert_id)
    if alert is None:
        raise HTTPException(404, "alert not found")
    report = None
    if alert.ai_summary:
        report = DiagnosticReport(
            matched=alert.match_status == "matched",
            best_similarity=alert.similarity_score or 0.0,
            plain_language=alert.ai_summary,
            user_actions="",
            engineer_guide=alert.knowledge.engineer_guide if alert.knowledge else "",
        )
    return AlertWithReport(**AlertRead.model_validate(alert).model_dump(), report=report)
