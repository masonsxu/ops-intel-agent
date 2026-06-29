import pytest

from ops_intel_agent.core.aggregator import AlertAggregator
from ops_intel_agent.schemas.alert import AlertCreate


@pytest.mark.asyncio
async def test_similar_alerts_form_cluster():
    agg = AlertAggregator(window_seconds=300, min_cluster_size=2, similarity_threshold=0.5)
    a = AlertCreate(service="s1", raw_log="HikariPool connection not available timeout 30000ms")
    b = AlertCreate(
        service="s2", raw_log="HikariPool connection is not available request timed out 30000ms"
    )
    assert await agg.offer(a) is None
    key = await agg.offer(b)
    assert key is not None  # absorbed into cluster
