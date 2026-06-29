"""OpenAI embedding provider (production). Lazily imports the SDK."""

from __future__ import annotations

from .base import EmbeddingProvider


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(
        self,
        api_key: str | None,
        base_url: str | None,
        model: str,
        dimension: int,
    ) -> None:
        if not api_key:
            raise ValueError("OPENAI API key is required for the openai embedding provider")
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._dim = dimension

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed_text(self, text: str) -> list[float]:
        res = await self._client.embeddings.create(
            input=text, model=self._model, dimensions=self._dim
        )
        return res.data[0].embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        res = await self._client.embeddings.create(
            input=texts, model=self._model, dimensions=self._dim
        )
        # OpenAI preserves input order in .data, but sort defensively by index.
        ordered = sorted(res.data, key=lambda d: d.index)
        return [d.embedding for d in ordered]
