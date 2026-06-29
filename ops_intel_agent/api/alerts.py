"""Alert ingestion & query endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
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
    limit: int = Query(50, ge=1, le=500),
    status_filter: str | None = Query(None, alias="status", description="open | resolved"),
    match_status: str | None = Query(
        None, description="matched | new_incident | aggregated | deposited"
    ),
    service: str | None = Query(None, description="Exact service name"),
    date: str | None = Query(None, description="Exact local date YYYY-MM-DD"),
    date_from: str | None = Query(None, description="Inclusive lower bound YYYY-MM-DD"),
    date_to: str | None = Query(None, description="Inclusive upper bound YYYY-MM-DD"),
    q: str | None = Query(None, description="Substring search on raw log / error message"),
    session: AsyncSession = Depends(db_session),
) -> list[AlertRead]:
    stmt = select(ErrorAlert).order_by(ErrorAlert.created_at.desc()).limit(limit)
    if status_filter:
        stmt = stmt.where(ErrorAlert.status == status_filter)
    if match_status:
        stmt = stmt.where(ErrorAlert.match_status == match_status)
    if service:
        stmt = stmt.where(ErrorAlert.service == service)
    if date:
        # func.date() collapses the timestamp to its local calendar date.
        stmt = stmt.where(func.date(ErrorAlert.created_at) == date)
    if date_from:
        stmt = stmt.where(func.date(ErrorAlert.created_at) >= date_from)
    if date_to:
        stmt = stmt.where(func.date(ErrorAlert.created_at) <= date_to)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(ErrorAlert.raw_log.ilike(like), ErrorAlert.error_message.ilike(like)))
    res = await session.execute(stmt)
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
