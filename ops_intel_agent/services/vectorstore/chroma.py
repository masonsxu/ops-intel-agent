"""Local persistent vector store backed by an embedded ChromaDB.

Chroma runs fully in-process and persists to a directory of SQLite + Parquet
files (path = `OIA_CHROMA_PATH`), so it is the default vector store for local
development and testing: real HNSW-backed ANN retrieval with **zero external
services**. The same `VectorStore` contract is honored so the pipeline is
agnostic to the backend.

Design notes
------------
* Each namespace maps to a Chroma collection named ``oia_<namespace>`` so we
  can reuse one client for multiple corpora (today only ``"knowledge"``).
* Chroma stores string ids; we convert the relational int id <-> ``str(id)``
  and also carry it in the row's metadata (``ref_id``) for a safe round-trip.
* With ``hnsw:space=cosine`` the reported *distance* equals
  ``1 - cosine_similarity``; we flip it back to a similarity score so the rest
  of the pipeline (threshold, UI) keeps using "higher = better".
* The Chroma client is synchronous; every call is dispatched via
  ``asyncio.to_thread`` to stay non-blocking on the FastAPI event loop.
"""

from __future__ import annotations

import asyncio
from typing import Any

from .base import VectorMatch, VectorRecord, VectorStore


# With hnsw:space=cosine the reported distance is (1 - cosine_similarity); flip
# it back to a similarity score so "higher = better" everywhere downstream.
def _dist_to_sim(dist: float) -> float:
    return 1.0 - float(dist)


def _collection_name(namespace: str) -> str:
    """Namespace -> a Chroma-safe collection name (3-63 chars, [A-Za-z0-9_-])."""
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in namespace)
    name = f"oia_{safe}"
    return name[:63].ljust(3, "_")


class ChromaVectorStore(VectorStore):
    """VectorStore implementation over a persistent, embedded ChromaDB."""

    def __init__(self, path: str = "./chroma_db") -> None:
        import chromadb

        # PersistentClient writes to disk so data survives restarts.
        self._client = chromadb.PersistentClient(path=path)
        self._path = path

    # ------------------------------------------------------------------ helpers
    def _collection(self, namespace: str) -> Any:
        return self._client.get_or_create_collection(
            name=_collection_name(namespace),
            metadata={"hnsw:space": "cosine"},
        )

    @staticmethod
    def _is_zero(vec: list[float]) -> bool:
        return not any(vec)

    # ------------------------------------------------------------------ API
    async def upsert(self, record: VectorRecord) -> None:
        # Chroma rejects all-zero vectors under cosine; guard so a degenerate
        # embedding (empty text) doesn't poison the store.
        if self._is_zero(record.embedding):
            return
        col = self._collection(record.namespace)
        await asyncio.to_thread(
            col.upsert,
            ids=[str(record.id)],
            embeddings=[list(record.embedding)],
            documents=[record.text],
            metadatas=[{"ref_id": record.id}],
        )

    async def search(self, namespace: str, query: list[float], k: int = 3) -> list[VectorMatch]:
        if self._is_zero(query):
            return []
        col = self._collection(namespace)
        if await asyncio.to_thread(col.count) == 0:
            return []
        res = await asyncio.to_thread(
            col.query,
            query_embeddings=[list(query)],
            n_results=k,
            include=["metadatas", "documents", "distances"],
        )
        ids = (res.get("ids") or [[]])[0]
        distances = (res.get("distances") or [[]])[0]
        documents = (res.get("documents") or [[]])[0]
        metadatas = (res.get("metadatas") or [[]])[0]
        matches: list[VectorMatch] = []
        for cid, dist, doc, meta in zip(ids, distances, documents, metadatas, strict=False):
            ref_id = int(meta.get("ref_id", cid)) if meta else int(cid)
            matches.append(VectorMatch(id=ref_id, score=_dist_to_sim(dist), text=doc or ""))
        return matches

    async def delete(self, namespace: str, id: int) -> None:
        col = self._collection(namespace)
        await asyncio.to_thread(col.delete, ids=[str(id)])

    async def count(self, namespace: str) -> int:
        col = self._collection(namespace)
        return int(await asyncio.to_thread(col.count))
