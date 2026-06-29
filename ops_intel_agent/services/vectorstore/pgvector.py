"""Production vector store backed by PostgreSQL + pgvector.

Uses a dedicated table (`vector_index`) to store embeddings so the relational
schema stays portable. Requires the `pgvector` extension and the asyncpg
driver. Connections are created lazily so importing this module never requires
a live database.
"""

from __future__ import annotations

from .base import VectorMatch, VectorRecord, VectorStore

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS vector_index (
    namespace TEXT NOT NULL,
    ref_id    BIGINT NOT NULL,
    text      TEXT NOT NULL,
    embedding vector(%(dim)s) NOT NULL,
    PRIMARY KEY (namespace, ref_id)
);
"""

_SEARCH_SQL = """
SELECT ref_id, text, 1 - (embedding <=> %(q)s) AS score
FROM vector_index
WHERE namespace = %(ns)s
ORDER BY embedding <=> %(q)s
LIMIT %(k)s;
"""


class PgVectorStore(VectorStore):
    def __init__(self, conn_str: str, dim: int = 1536) -> None:
        self._conn_str = conn_str
        self._dim = dim
        self._pool = None
        self._ready = False

    async def _ensure(self) -> None:
        if self._ready:
            return
        import asyncpg
        from pgvector.asyncpg import register_vector

        self._pool = await asyncpg.create_pool(self._conn_str, min_size=1, max_size=8)
        async with self._pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            await register_vector(conn)
            await conn.execute(_CREATE_SQL, dim=self._dim)
        self._ready = True

    async def upsert(self, record: VectorRecord) -> None:
        await self._ensure()
        from pgvector.asyncpg import register_vector

        async with self._pool.acquire() as conn:
            await register_vector(conn)
            await conn.execute(
                """
                INSERT INTO vector_index (namespace, ref_id, text, embedding)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (namespace, ref_id)
                DO UPDATE SET text = EXCLUDED.text, embedding = EXCLUDED.embedding;
                """,
                record.namespace,
                record.id,
                record.text,
                record.embedding,
            )

    async def search(self, namespace: str, query: list[float], k: int = 3) -> list[VectorMatch]:
        await self._ensure()
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(_SEARCH_SQL, ns=namespace, q=query, k=k)
        return [VectorMatch(id=r["ref_id"], score=float(r["score"]), text=r["text"]) for r in rows]

    async def delete(self, namespace: str, id: int) -> None:
        await self._ensure()
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM vector_index WHERE namespace=$1 AND ref_id=$2",
                namespace,
                id,
            )

    async def count(self, namespace: str) -> int:
        await self._ensure()
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT count(*) AS c FROM vector_index WHERE namespace=$1",
                namespace,
            )
        return int(row["c"]) if row else 0
