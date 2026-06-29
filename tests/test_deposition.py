import pytest

from ops_intel_agent.core.deposition import DepositionService
from ops_intel_agent.core.pipeline import TriagePipeline
from ops_intel_agent.schemas.alert import AlertCreate
from ops_intel_agent.schemas.knowledge import KnowledgeDepositionRequest


@pytest.mark.asyncio
async def test_deposition_creates_matchable_knowledge(db_session):
    pipeline = TriagePipeline()
    ds = DepositionService()
    novel = "quantum flux capacitor desynchronized in phase shift reactor 47"

    first = await pipeline.process(db_session, AlertCreate(service="r", raw_log=novel))
    assert first.alert.match_status == "new_incident"
    alert_id = first.alert.id

    kb = await ds.deposit(
        db_session,
        KnowledgeDepositionRequest(
            alert_id=alert_id,
            root_cause="flux capacitor needed recalibration",
            resolution="recalibrate the flux capacitor to 1.21 gigawatts",
            engineer="doc",
            tags=["flux"],
        ),
    )
    assert kb.user_guide
    assert "1.21 gigawatts" in kb.engineer_guide

    second = await pipeline.process(db_session, AlertCreate(service="r2", raw_log=novel))
    assert second.alert.match_status == "matched"
    assert second.alert.matched_knowledge_id == kb.id
