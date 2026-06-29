"""In-process vector store backed by numpy, with disk persistence.

Good enough for local development, tests, and single-replica deployments.
Vectors are keyed by (namespace, id) so the same store can serve multiple
corpora (e.g. "knowledge" vs "runbooks"). State is persisted to a JSON file so
offline mode survives process restarts — you can seed in one process and serve
from another without a real database.
"""

from __future__ import annotations

import json
import os
import threading

import numpy as np

from .base import VectorMatch, VectorRecord, VectorStore

_MAGIC = "__ops_intel_vectors_v1__"


class MemoryVectorStore(VectorStore):
    def __init__(self, persist_path: str | None = None) -> None:
        self._lock = threading.Lock()
        self._persist_path = persist_path
        # namespace -> {id: [text, embedding]}
        self._data: dict[str, dict[int, list]] = {}
        self._loaded = False

    # -- persistence -------------------------------------------------------
    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._persist_path or not os.path.exists(self._persist_path):
            return
        try:
            with open(self._persist_path, encoding="utf-8") as fh:
                blob = json.load(fh)
            if isinstance(blob, dict) and blob.get("magic") == _MAGIC:
                for ns, items in blob.get("data", {}).items():
                    self._data[ns] = {int(k): v for k, v in items.items()}
        except (OSError, ValueError, json.JSONDecodeError):
            pass  # corrupt file -> start empty

    def _persist(self) -> None:
        if not self._persist_path:
            return
        tmp = f"{self._persist_path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(
                {"magic": _MAGIC, "data": self._data},
                fh,
                ensure_ascii=False,
            )
        os.replace(tmp, self._persist_path)

    # -- public API --------------------------------------------------------
    async def upsert(self, record: VectorRecord) -> None:
        with self._lock:
            self._load()
            ns = self._data.setdefault(record.namespace, {})
            ns[record.id] = [record.text, list(record.embedding)]
            self._persist()

    async def search(self, namespace: str, query: list[float], k: int = 3) -> list[VectorMatch]:
        with self._lock:
            self._load()
            ns = self._data.get(namespace, {})
            if not ns:
                return []
            ids = list(ns.keys())
            matrix = np.vstack([np.asarray(ns[i][1], dtype=np.float32) for i in ids])
            texts = [ns[i][0] for i in ids]
        q = np.asarray(query, dtype=np.float32)
        qn = np.linalg.norm(q)
        if qn == 0:
            return []
        q = q / qn
        norms = np.linalg.norm(matrix, axis=1)
        safe = np.where(norms == 0, 1.0, norms)
        normed = matrix / safe[:, None]
        sims = normed @ q
        order = np.argsort(-sims)[:k]
        return [VectorMatch(id=int(ids[i]), score=float(sims[i]), text=texts[i]) for i in order]

    async def delete(self, namespace: str, id: int) -> None:
        with self._lock:
            self._load()
            if namespace in self._data:
                self._data[namespace].pop(id, None)
                self._persist()

    async def count(self, namespace: str) -> int:
        with self._lock:
            self._load()
            return len(self._data.get(namespace, {}))
