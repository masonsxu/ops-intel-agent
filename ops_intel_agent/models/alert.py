"""Live anomaly alerts ingested from monitoring / log agents."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from .knowledge import ErrorKnowledgeBase


# NOTE: status literals live here so both model & schema import one source.
AlertStatus = Enum  # we'll pass python literals; mapped via String column below


class ErrorAlert(Base, TimestampMixin):
    __tablename__ = "error_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Correlation id supplied by the upstream monitor (optional).
    external_id: Mapped[str | None] = mapped_column(String(128), index=True)
    server_ip: Mapped[str | None] = mapped_column(String(64), index=True)
    host: Mapped[str | None] = mapped_column(String(255))
    service: Mapped[str | None] = mapped_column(String(255), index=True)
    severity: Mapped[str] = mapped_column(String(32), default="error")
    raw_log: Mapped[str] = mapped_column(Text)
    # Structured fields extracted by the log parser.
    error_message: Mapped[str | None] = mapped_column(Text)
    stack_trace: Mapped[str | None] = mapped_column(Text)

    matched_knowledge_id: Mapped[int | None] = mapped_column(
        ForeignKey("error_knowledge_base.id", ondelete="SET NULL"), index=True
    )
    similarity_score: Mapped[float | None] = mapped_column(Float)
    # "matched" | "new_incident" | "aggregated"
    match_status: Mapped[str] = mapped_column(String(32), default="new_incident")
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|resolved
    ai_summary: Mapped[str | None] = mapped_column(Text)
    cluster_key: Mapped[str | None] = mapped_column(String(128), index=True)

    knowledge: Mapped[ErrorKnowledgeBase | None] = relationship(
        back_populates="alerts", lazy="selectin"
    )

    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
