import asyncio

from ops_intel_agent.services.vectorstore import VectorRecord, get_vector_store


def test_upsert_search_delete():
    store = get_vector_store()
    base = [0.0] * 256

    async def run():
        for i, txt in enumerate(["redis timeout", "redis refused", "mysql pool"]):
            v = list(base)
            v[i] = 1.0
            await store.upsert(VectorRecord(namespace="knowledge", id=i, text=txt, embedding=v))
        query = list(base)
        query[0] = 1.0
        hits = await store.search("knowledge", query, k=2)
        assert hits[0].id == 0
        assert await store.count("knowledge") == 3
        await store.delete("knowledge", 0)
        assert await store.count("knowledge") == 2

    asyncio.run(run())


def test_empty_namespace_returns_nothing():
    store = get_vector_store()
    hits = asyncio.run(store.search("missing", [0.0] * 256, k=3))
    assert hits == []
