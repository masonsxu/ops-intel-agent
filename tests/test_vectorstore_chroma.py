"""Tests for the embedded ChromaVectorStore.

These only run when the optional `chromadb` package is installed (it is a core
dependency in pyproject.toml, so it should be). The default test suite still
runs against the in-memory store via tests/conftest.py.
"""

from __future__ import annotations

import asyncio

import pytest

chromadb = pytest.importorskip("chromadb")  # noqa: F841

from ops_intel_agent.services.vectorstore import VectorRecord  # noqa: E402
from ops_intel_agent.services.vectorstore.chroma import ChromaVectorStore  # noqa: E402


def _store(tmp_path):
    return ChromaVectorStore(path=str(tmp_path / "chroma"))


def test_upsert_search_delete(tmp_path):
    store = _store(tmp_path)
    base = [0.0] * 256

    async def run():
        for i, txt in enumerate(["redis timeout", "redis refused", "mysql pool exhausted"]):
            v = list(base)
            v[i] = 1.0
            await store.upsert(VectorRecord(namespace="knowledge", id=i, text=txt, embedding=v))
        # sanity: count
        assert await store.count("knowledge") == 3
        # query closest to vector 0 -> should rank id 0 first
        query = list(base)
        query[0] = 1.0
        hits = await store.search("knowledge", query, k=2)
        assert hits[0].id == 0
        assert hits[0].score > 0.5
        # delete
        await store.delete("knowledge", 0)
        assert await store.count("knowledge") == 2

    asyncio.run(run())


def test_empty_namespace_search(tmp_path):
    store = _store(tmp_path)

    async def run():
        hits = await store.search("missing", [0.0] * 256, k=3)
        assert hits == []
        # count on a never-touched namespace is 0
        assert await store.count("missing") == 0

    asyncio.run(run())


def test_zero_vector_is_noop(tmp_path):
    """All-zero embeddings must not raise (cosine guard)."""
    store = _store(tmp_path)

    async def run():
        await store.upsert(VectorRecord(namespace="knowledge", id=9, text="x", embedding=[0.0] * 8))
        assert await store.count("knowledge") == 0
        assert await store.search("knowledge", [0.0] * 8, k=3) == []

    asyncio.run(run())
