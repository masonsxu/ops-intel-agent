"""Abstract vector store interface."""

from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass(slots=True)
class VectorRecord:
    namespace: str  # e.g. "knowledge"
    id: int  # the relational row id this vector refers to
    text: str
    embedding: list[float]


@dataclass(slots=True)
class VectorMatch:
    id: int
    score: float
    text: str


class VectorStore(abc.ABC):
    """Owns embeddings and similarity search, decoupled from the RDBMS."""

    @abc.abstractmethod
    async def upsert(self, record: VectorRecord) -> None: ...

    @abc.abstractmethod
    async def search(self, namespace: str, query: list[float], k: int = 3) -> list[VectorMatch]: ...

    @abc.abstractmethod
    async def delete(self, namespace: str, id: int) -> None: ...

    @abc.abstractmethod
    async def count(self, namespace: str) -> int: ...


_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        from ...config import get_settings

        settings = get_settings()
        if settings.vector_store == "pgvector":
            from .pgvector import PgVectorStore

            _store = PgVectorStore(settings.pg_connection_string)
        elif settings.vector_store == "chroma":
            from .chroma import ChromaVectorStore

            _store = ChromaVectorStore(path=settings.chroma_path)
        else:
            from .memory import MemoryVectorStore

            _store = MemoryVectorStore(persist_path=settings.memory_vector_path)
    return _store
