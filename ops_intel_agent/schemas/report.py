"""Schemas describing the AI diagnostic report and notification payload."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .action import ActionSpec


class RetrievalHit(BaseModel):
    """A single retrieved historical case."""

    knowledge_id: int
    title: str
    similarity: float
    error_type: str | None = None
    user_guide: str | None = None
    engineer_guide: str | None = None


class DiagnosticReport(BaseModel):
    """The structured output of the LLM triage step."""

    matched: bool = Field(..., description="Whether a confident match was found")
    best_similarity: float
    plain_language: str = Field(..., description="Plain-language explanation for end users")
    user_actions: str = Field(..., description="Concrete next steps for users")
    engineer_guide: str = Field(..., description="Technical playbook for SREs")
    suggested_actions: list[ActionSpec] = Field(default_factory=list)
    retrieval: list[RetrievalHit] = Field(default_factory=list)
    cluster_summary: str | None = None

    model_config = {"from_attributes": True}


class NotificationPayload(BaseModel):
    """The rendered notification sent to the work-group bot."""

    title: str
    markdown: str
    suggested_actions: list[ActionSpec] = Field(default_factory=list)
    alert_ids: list[int] = Field(default_factory=list)
