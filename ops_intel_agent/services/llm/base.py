"""Abstract LLM provider and service wrapper."""

from __future__ import annotations

import abc

from ...schemas.knowledge import KnowledgeDepositionRequest
from ...schemas.report import DiagnosticReport


class LLMProvider(abc.ABC):
    """Minimal chat-completion-style interface we depend on."""

    @abc.abstractmethod
    async def complete(self, system: str, user: str) -> str: ...


class LLMService:
    """Higher-level orchestration built on top of an LLMProvider.

    Keeps prompt assembly out of the pipeline so the pipeline stays readable,
    and so we can unit-test the prompts independently.
    """

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider
        # Import lazily to avoid a circular import at module load time.
        from ...prompts.templates import (
            build_deposition_prompt,
            build_triage_prompt,
        )

        self._build_triage_prompt = build_triage_prompt
        self._build_deposition_prompt = build_deposition_prompt

    async def triage(self, ctx: dict) -> DiagnosticReport:
        system, user = self._build_triage_prompt(ctx)
        raw = await self.provider.complete(system, user)
        return _parse_triage_output(raw, ctx)

    async def build_knowledge(self, req: KnowledgeDepositionRequest, raw_log: str) -> dict:
        system, user = self._build_deposition_prompt(req, raw_log)
        raw = await self.provider.complete(system, user)
        return _parse_deposition_output(raw, req)


# --- helpers ---------------------------------------------------------------
def _parse_triage_output(raw: str, ctx: dict) -> DiagnosticReport:
    from ...prompts.templates import parse_triage_markdown

    parsed = parse_triage_markdown(raw)
    retrieval = ctx.get("retrieval") or []
    best = retrieval[0]["similarity"] if retrieval else 0.0
    matched = bool(ctx.get("matched"))
    return DiagnosticReport(
        matched=matched,
        best_similarity=float(best),
        plain_language=parsed["plain_language"],
        user_actions=parsed["user_actions"],
        engineer_guide=parsed["engineer_guide"],
        suggested_actions=ctx.get("suggested_actions") or [],
        retrieval=[
            {
                "knowledge_id": r["knowledge_id"],
                "title": r["title"],
                "similarity": r["similarity"],
                "error_type": r.get("error_type"),
                "user_guide": r.get("user_guide"),
                "engineer_guide": r.get("engineer_guide"),
            }
            for r in retrieval
        ],
        cluster_summary=ctx.get("cluster_summary"),
    )


def _parse_deposition_output(raw: str, req: KnowledgeDepositionRequest) -> dict:
    from ...prompts.templates import parse_deposition_markdown

    parsed = parse_deposition_markdown(raw)
    return {
        "error_type": parsed.get("error_type") or req.error_type,
        "title": parsed.get("title") or f"{req.error_type or 'Incident'} - {req.root_cause[:60]}",
        "raw_log_sample": req.__dict__,  # replaced by caller with actual log
        "root_cause": parsed.get("root_cause") or req.root_cause,
        "user_guide": parsed.get("user_guide") or "联系值班工程师确认影响范围。",
        "engineer_guide": parsed.get("engineer_guide") or req.resolution,
        "tags": req.tags,
    }


_provider: LLMProvider | None = None


def get_llm_service() -> LLMService:
    global _provider
    if _provider is None:
        from ...config import get_settings

        settings = get_settings()
        if settings.llm_provider == "openai":
            from .openai import OpenAILLMProvider

            _provider = OpenAILLMProvider(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                model=settings.llm_model,
                temperature=settings.llm_temperature,
            )
        else:
            from .local import LocalLLMProvider

            _provider = LocalLLMProvider()
    return LLMService(_provider)
