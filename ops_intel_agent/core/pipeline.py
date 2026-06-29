"""The end-to-end triage pipeline.

This is the orchestrator that ties every pluggable service together:

    raw log
      -> parse  (extract error/stack/ip/service)
      -> embed  (vectorize canonical text)
      -> search (RAG: find top-K similar historical cases)
      -> decide (match vs. new incident, via similarity threshold)
      -> triage (LLM produces plain-language + engineer guide)
      -> suggest actions (function-calling button suggestions)
      -> persist alert + emit notification

It deliberately contains *no* I/O of its own beyond the injected services, so
the whole thing is unit-testable with fakes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from ..extractors import parse_log
from ..logging import get_logger
from ..models import ErrorAlert, ErrorKnowledgeBase
from ..schemas.alert import AlertCreate
from ..schemas.report import DiagnosticReport, NotificationPayload, RetrievalHit
from ..services.actions import get_action_registry
from ..services.embeddings import get_embedding_service
from ..services.llm import get_llm_service
from ..services.notifier import get_notifier
from ..services.vectorstore import get_vector_store

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from ..config import Settings

log = get_logger(__name__)

KNOWLEDGE_NS = "knowledge"


@dataclass
class TriageResult:
    alert: ErrorAlert
    report: DiagnosticReport
    notification: NotificationPayload | None


class TriagePipeline:
    def __init__(self, settings: Settings | None = None) -> None:
        from ..config import get_settings

        self.settings = settings or get_settings()
        self.embeddings = get_embedding_service()
        self.llm = get_llm_service()
        self.store = get_vector_store()
        self.actions = get_action_registry()
        self.notifier = get_notifier()

    # ------------------------------------------------------------------
    async def _retrieve(
        self, session: AsyncSession, query_vec: list[float], k: int
    ) -> tuple[list[ErrorKnowledgeBase], list[dict]]:
        matches = await self.store.search(KNOWLEDGE_NS, query_vec, k=k)
        if not matches:
            return [], []
        ids = [m.id for m in matches]
        rows = (
            (
                await session.execute(
                    select(ErrorKnowledgeBase).where(
                        ErrorKnowledgeBase.id.in_(ids),
                        ErrorKnowledgeBase.is_active.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        by_id = {r.id: r for r in rows}
        ordered = []
        retrieval: list[dict] = []
        for m in matches:
            kb = by_id.get(m.id)
            if not kb:
                continue
            ordered.append(kb)
            retrieval.append(
                {
                    "knowledge_id": kb.id,
                    "title": kb.title,
                    "similarity": m.score,
                    "error_type": kb.error_type,
                    "raw_log": kb.raw_log_sample,
                    "user_guide": kb.user_guide,
                    "engineer_guide": kb.engineer_guide,
                    "root_cause": kb.root_cause,
                }
            )
        return ordered, retrieval

    # ------------------------------------------------------------------
    async def process(
        self,
        session: AsyncSession,
        payload: AlertCreate,
        *,
        notify: bool = True,
        cluster_summary: str | None = None,
    ) -> TriageResult:
        extraction = parse_log(payload.raw_log)
        query_vec = await self.embeddings.embed(extraction.canonical_text)

        k = self.settings.similarity_top_k
        _, retrieval = await self._retrieve(session, query_vec, k)

        best_sim = retrieval[0]["similarity"] if retrieval else 0.0
        matched = best_sim >= self.settings.similarity_threshold and bool(retrieval)

        # Increment occurrence_count on the matched knowledge row.
        matched_kb_id: int | None = None
        if matched:
            matched_kb_id = retrieval[0]["knowledge_id"]
            await self._bump_occurrence(session, matched_kb_id)

        # LLM triage.
        suggested: list = []
        if matched and self.settings.enable_action_suggestions:
            rc = (retrieval[0].get("root_cause") or "") + " " + retrieval[0]["title"]
            suggested = self.actions.suggest_for(
                rc, best_sim, self.settings.action_confidence_threshold
            )

        triage_ctx = {
            "current_log": payload.raw_log,
            "retrieval": retrieval,
            "matched": matched,
            "suggested_actions": [s.model_dump() for s in suggested],
            "cluster_summary": cluster_summary,
        }
        report = await self.llm.triage(triage_ctx)

        # Persist the alert.
        alert = ErrorAlert(
            external_id=payload.external_id,
            server_ip=payload.server_ip or extraction.server_ip,
            host=payload.host,
            service=payload.service or extraction.service,
            severity=extraction.severity,
            raw_log=payload.raw_log,
            error_message=extraction.error_message,
            stack_trace=extraction.stack_trace,
            matched_knowledge_id=matched_kb_id,
            similarity_score=best_sim,
            match_status="matched" if matched else "new_incident",
            ai_summary=report.plain_language,
        )
        session.add(alert)
        await session.flush()

        retrieval_objs = [
            RetrievalHit(
                knowledge_id=r["knowledge_id"],
                title=r["title"],
                similarity=r["similarity"],
                error_type=r.get("error_type"),
                user_guide=r.get("user_guide"),
                engineer_guide=r.get("engineer_guide"),
            )
            for r in retrieval
        ]
        report.retrieval = retrieval_objs

        # Decide whether to notify.
        notification: NotificationPayload | None = None
        should_notify = notify and (matched or self.settings.notify_on_new_incident)
        if should_notify:
            notification = self._build_notification(alert, report)
            await self.notifier.send(notification)

        await session.commit()
        log.info(
            "triage.complete",
            alert_id=alert.id,
            matched=matched,
            similarity=best_sim,
            match_status=alert.match_status,
        )
        return TriageResult(alert=alert, report=report, notification=notification)

    # ------------------------------------------------------------------
    async def _bump_occurrence(self, session: AsyncSession, knowledge_id: int) -> None:
        kb = await session.get(ErrorKnowledgeBase, knowledge_id)
        if kb is not None:
            kb.occurrence_count = (kb.occurrence_count or 1) + 1

    # ------------------------------------------------------------------
    def _build_notification(
        self, alert: ErrorAlert, report: DiagnosticReport
    ) -> NotificationPayload:
        from ..schemas.action import ActionSpec

        status_emoji = "🟡" if report.matched else "🔴"
        title = f"{status_emoji} 服务异常告警 · {alert.service or alert.host or '未知服务'}"
        actions = [
            ActionSpec(
                name=a["name"],
                label=a["label"],
                description=a["description"],
                risk_level=a["risk_level"],
                params={"alert_id": str(alert.id)},
            )
            for a in ([s.model_dump() for s in report.suggested_actions])
        ]
        retrieval_lines = "".join(
            f"  - {r.title} (相似度 {r.similarity:.2f})\n" for r in report.retrieval
        )
        markdown = (
            f"**服务**: {alert.service or alert.host or '-'}  "
            f"**主机**: {alert.server_ip or '-'}  "
            f"**时间**: {alert.created_at:%Y-%m-%d %H:%M:%S}\n\n"
            f"{report.plain_language}\n\n"
            f"**您可以采取的行动**\n{report.user_actions}\n\n"
            f"<details><summary>技术排查参考（点击展开）</summary>\n\n"
            f"{report.engineer_guide}\n\n</details>\n\n"
            + (f"**历史相似案例**\n{retrieval_lines}" if retrieval_lines else "")
        )
        return NotificationPayload(
            title=title,
            markdown=markdown,
            suggested_actions=actions,
            alert_ids=[alert.id],
        )
