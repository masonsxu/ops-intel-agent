"""Remediation actions (function-calling targets) and their invocations."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base, TimestampMixin


class RemediationAction(Base, TimestampMixin):
    """Catalog of executable remediation actions the bot can offer/run."""

    __tablename__ = "remediation_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text)
    # Safety classification gating whether it can auto-run or needs approval.
    risk_level: Mapped[str] = mapped_column(String(16), default="low")
    is_enabled: Mapped[bool] = mapped_column(default=True)


class ActionInvocation(Base, TimestampMixin):
    """Audit log of every remediation action executed via the bot."""

    __tablename__ = "action_invocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action_name: Mapped[str] = mapped_column(String(64), index=True)
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("error_alerts.id", ondelete="SET NULL"))
    knowledge_id: Mapped[int | None] = mapped_column(
        ForeignKey("error_knowledge_base.id", ondelete="SET NULL")
    )
    target: Mapped[str | None] = mapped_column(String(255))
    triggered_by: Mapped[str] = mapped_column(String(64), default="bot")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    result: Mapped[str | None] = mapped_column(Text)
