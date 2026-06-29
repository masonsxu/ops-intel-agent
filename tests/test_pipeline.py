import pytest

from ops_intel_agent.config import get_settings
from ops_intel_agent.core.pipeline import KNOWLEDGE_NS, TriagePipeline
from ops_intel_agent.models import ErrorKnowledgeBase
from ops_intel_agent.schemas.alert import AlertCreate
from ops_intel_agent.services.embeddings import get_embedding_service
from ops_intel_agent.services.vectorstore import VectorRecord, get_vector_store


async def _seed(session, log, **kw):
    kb = ErrorKnowledgeBase(
        title=kw["title"],
        raw_log_sample=log,
        user_guide=kw.get("user_guide", "u"),
        engineer_guide=kw["engineer_guide"],
        root_cause=kw.get("root_cause", ""),
        error_type=kw.get("error_type"),
        tags=",".join(kw.get("tags", [])),
    )
    session.add(kb)
    await session.flush()
    from ops_intel_agent.extractors import parse_log

    vec = await get_embedding_service().embed(parse_log(log).canonical_text)
    await get_vector_store().upsert(
        VectorRecord(namespace=KNOWLEDGE_NS, id=kb.id, text=log, embedding=vec)
    )
    await session.commit()
    return kb


@pytest.mark.asyncio
async def test_known_incident_matches(db_session, monkeypatch):
    monkeypatch.setenv("OIA_SIMILARITY_THRESHOLD", "0.6")
    get_settings.cache_clear()
    pipeline = TriagePipeline()
    kb = await _seed(
        db_session,
        "ERROR JedisConnectionException redis connection refused timeout 10.0.1.2:6379",
        title="redis timeout",
        engineer_guide="restart redis",
        root_cause="redis oom",
        error_type="Redis",
    )
    res = await pipeline.process(
        db_session,
        AlertCreate(
            service="auth",
            raw_log="JedisConnectionException Failed connecting to redis connection timed out",
        ),
    )
    assert res.alert.match_status == "matched"
    assert res.alert.matched_knowledge_id == kb.id
    assert res.report.matched is True
    assert res.alert.similarity_score > 0.6
    # occurrence_count should have incremented
    assert kb.occurrence_count >= 2


@pytest.mark.asyncio
async def test_novel_incident_is_flagged(db_session):
    pipeline = TriagePipeline()
    res = await pipeline.process(
        db_session,
        AlertCreate(
            service="x", raw_log="quantum flux capacitor desynchronized in phase shift reactor"
        ),
    )
    assert res.alert.match_status == "new_incident"
    assert res.report.matched is False
    assert res.report.best_similarity < 0.78


@pytest.mark.asyncio
async def test_action_buttons_for_cache_incident(db_session, monkeypatch):
    monkeypatch.setenv("OIA_SIMILARITY_THRESHOLD", "0.5")
    monkeypatch.setenv("OIA_ACTION_CONFIDENCE_THRESHOLD", "0.5")
    get_settings.cache_clear()
    pipeline = TriagePipeline()
    await _seed(
        db_session,
        "ERROR redis cache oom connection refused",
        title="redis oom",
        engineer_guide="clear cache",
        root_cause="redis cache oom",
        error_type="Redis",
    )
    res = await pipeline.process(
        db_session, AlertCreate(service="s", raw_log="redis cache oom connection refused")
    )
    action_names = [a.name for a in res.report.suggested_actions]
    assert "clear_cache" in action_names
    assert len(action_names) == len(set(action_names))  # no duplicates
