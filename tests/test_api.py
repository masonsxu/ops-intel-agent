import pytest
from httpx import ASGITransport, AsyncClient

from ops_intel_agent.api.deps import db_session as db_session_dep
from ops_intel_agent.main import create_app


@pytest.fixture
def app(db_session):
    """App with its DB dependency overridden to the isolated in-memory session."""
    application = create_app()

    async def _override():
        yield db_session

    application.dependency_overrides[db_session_dep] = _override
    return application


@pytest.mark.asyncio
async def test_health_and_ready(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        h = await ac.get("/health")
        assert h.status_code == 200
        assert h.json()["status"] == "ok"
        r = await ac.get("/ready")
        assert r.status_code == 200
        assert r.json()["vector_store"] == "memory"


@pytest.mark.asyncio
async def test_alert_lifecycle_via_api(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.post(
            "/alerts", json={"service": "x", "raw_log": "novel problem zzz quantum flux"}
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["match_status"] == "new_incident"
        assert body["report"]["matched"] is False

        listing = await ac.get("/alerts")
        assert listing.status_code == 200
        assert len(listing.json()) >= 1

        actions = await ac.get("/actions")
        assert actions.status_code == 200
        names = {a["name"] for a in actions.json()}
        assert "restart_service" in names


@pytest.mark.asyncio
async def test_create_knowledge_and_match(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        k = await ac.post(
            "/knowledge",
            json={
                "title": "redis oom",
                "raw_log_sample": "redis OOM connection refused cache",
                "user_guide": "缓存故障，请稍后重试",
                "engineer_guide": "重启 redis 并扩容",
                "tags": ["redis"],
            },
        )
        assert k.status_code == 201

        a = await ac.post(
            "/alerts",
            json={"service": "s", "raw_log": "redis OOM connection refused cache timeout"},
        )
        body = a.json()
        assert body["match_status"] == "matched"
        assert body["matched_knowledge_id"] == k.json()["id"]
