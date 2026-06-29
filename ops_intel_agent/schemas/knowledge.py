"""Schemas for the knowledge base CRUD and the deposition flow."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class KnowledgeCreate(BaseModel):
    error_type: str | None = None
    title: str
    raw_log_sample: str
    root_cause: str | None = None
    user_guide: str
    engineer_guide: str
    tags: list[str] = Field(default_factory=list)
    source: str = "manual"

    model_config = {"from_attributes": True}


class KnowledgeRead(BaseModel):
    id: int
    error_type: str | None = None
    title: str
    raw_log_sample: str
    root_cause: str | None = None
    user_guide: str
    engineer_guide: str
    occurrence_count: int
    source: str
    tags: list[str] = Field(default_factory=list)
    confidence: float
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm(cls, obj):  # type: ignore[override]
        return cls(
            id=obj.id,
            error_type=obj.error_type,
            title=obj.title,
            raw_log_sample=obj.raw_log_sample,
            root_cause=obj.root_cause,
            user_guide=obj.user_guide,
            engineer_guide=obj.engineer_guide,
            occurrence_count=obj.occurrence_count,
            source=obj.source,
            tags=obj.tag_list(),
            confidence=obj.confidence,
            is_active=obj.is_active,
            created_at=obj.created_at,
        )


class KnowledgeDepositionRequest(BaseModel):
    """Engineer's free-form resolution notes for a new incident.

    The LLM turns this into structured knowledge base fields.
    """

    alert_id: int
    error_type: str | None = None
    root_cause: str = Field(..., description="What actually went wrong")
    resolution: str = Field(..., description="What the engineer did to resolve it")
    engineer: str = "engineer"
    tags: list[str] = Field(default_factory=list)
