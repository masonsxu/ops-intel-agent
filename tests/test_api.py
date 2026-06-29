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


@pytest.mark.asyncio
async def test_alerts_filters_by_status_and_text(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.post("/alerts", json={"service": "auth", "raw_log": "redis timeout boom"})
        await ac.post("/alerts", json={"service": "pay", "raw_log": "mysql pool exhausted"})

        by_text = await ac.get("/alerts", params={"q": "mysql"})
        assert by_text.status_code == 200
        rows = by_text.json()
        assert len(rows) == 1
        assert "mysql" in rows[0]["raw_log"]

        by_service = await ac.get("/alerts", params={"service": "auth"})
        assert all(r["service"] == "auth" for r in by_service.json())

        by_match = await ac.get("/alerts", params={"match_status": "new_incident"})
        assert all(r["match_status"] == "new_incident" for r in by_match.json())


@pytest.mark.asyncio
async def test_knowledge_semantic_search_and_date_filter(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.post(
            "/knowledge",
            json={
                "title": "redis oom",
                "raw_log_sample": "redis OOM connection refused cache",
                "user_guide": "缓存故障，请稍后重试",
                "engineer_guide": "重启 redis 并扩容",
                "tags": ["redis"],
                "error_type": "Redis 连接超时",
            },
        )

        # Vector fuzzy search: a phrased query still surfaces the redis entry.
        hits = await ac.get("/knowledge/search", params={"q": "cache connection timeout", "k": 3})
        assert hits.status_code == 200
        payload = hits.json()
        assert payload, "expected at least one semantic hit"
        assert "similarity" in payload[0]
        assert payload[0]["title"] == "redis oom"

        # Empty query is rejected by validation.
        bad = await ac.get("/knowledge/search", params={"q": ""})
        assert bad.status_code == 422

        # Date-scoped listing: today's date should include the entry.
        from datetime import date

        today = date.today().isoformat()
        on_day = await ac.get("/knowledge", params={"date": today})
        assert on_day.status_code == 200
        assert any(k["title"] == "redis oom" for k in on_day.json())

        # A clearly-empty date range returns nothing.
        none = await ac.get(
            "/knowledge", params={"date_from": "1999-01-01", "date_to": "1999-12-31"}
        )
        assert none.json() == []


@pytest.mark.asyncio
async def test_stats_endpoint(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.post("/alerts", json={"raw_log": "something broke xyz"})
        s = await ac.get("/stats")
        assert s.status_code == 200
        body = s.json()
        assert body["alerts"]["total"] >= 1
        assert body["alerts"]["new_incident"] >= 1
        assert "knowledge" in body and "vectors" in body["knowledge"]
