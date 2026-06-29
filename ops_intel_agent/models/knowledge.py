"""Historical incident knowledge base (the "experience" of senior engineers)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from .alert import ErrorAlert


class ErrorKnowledgeBase(Base, TimestampMixin):
    """A curated, auto-deposited record of a known error and its playbook.

    The raw embedding vector is *not* stored here on purpose: it lives in the
    pluggable vector store. This table holds only structured metadata plus the
    two human-targeted guides (plain-language for users, technical for SREs).
    """

    __tablename__ = "error_knowledge_base"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    error_type: Mapped[str | None] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(512))
    raw_log_sample: Mapped[str] = mapped_column(Text)
    root_cause: Mapped[str | None] = mapped_column(Text)
    user_guide: Mapped[str] = mapped_column(Text)
    engineer_guide: Mapped[str] = mapped_column(Text)
    # How many times this knowledge has matched a live alert.
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    # Curator: "auto" when deposited by the pipeline, or an engineer's name.
    source: Mapped[str] = mapped_column(String(64), default="auto")
    tags: Mapped[str | None] = mapped_column(Text)  # comma-separated
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    # Soft delete so we never lose history.
    is_active: Mapped[bool] = mapped_column(default=True)

    alerts: Mapped[list[ErrorAlert]] = relationship(back_populates="knowledge", lazy="selectin")

    def tag_list(self) -> list[str]:
        return [t.strip() for t in (self.tags or "").split(",") if t.strip()]
