"""Schemas for alert ingestion and display."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AlertCreate(BaseModel):
    """Inbound alert payload from a monitor / log agent."""

    external_id: str | None = None
    server_ip: str | None = None
    host: str | None = None
    service: str | None = None
    severity: str = "error"
    raw_log: str = Field(..., min_length=1, description="The raw log line / message")

    model_config = {"from_attributes": True}


class AlertRead(BaseModel):
    id: int
    external_id: str | None = None
    server_ip: str | None = None
    host: str | None = None
    service: str | None = None
    severity: str
    raw_log: str
    error_message: str | None = None
    matched_knowledge_id: int | None = None
    similarity_score: float | None = None
    match_status: str
    status: str
    ai_summary: str | None = None
    cluster_key: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertWithReport(AlertRead):
    """Alert plus the generated diagnostic report (if any)."""

    report: DiagnosticReport | None = None  # noqa: F821


# Resolve forward reference at import time.
from .report import DiagnosticReport  # noqa: E402

AlertWithReport.model_rebuild()
