"""Abstract embedding provider and a small service wrapper."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

from ...config import get_settings

if TYPE_CHECKING:
    pass


class EmbeddingProvider(abc.ABC):
    """Produces an L2-normalized embedding vector for a piece of text."""

    @property
    @abc.abstractmethod
    def dimension(self) -> int: ...

    @abc.abstractmethod
    async def embed_text(self, text: str) -> list[float]: ...

    @abc.abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class EmbeddingService:
    """Thin application-facing wrapper around an EmbeddingProvider."""

    def __init__(self, provider: EmbeddingProvider) -> None:
        self.provider = provider

    @property
    def dimension(self) -> int:
        return self.provider.dimension

    async def embed(self, text: str) -> list[float]:
        return await self.provider.embed_text(text)

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await self.provider.embed_batch(texts)


_provider: EmbeddingProvider | None = None


def get_embedding_service() -> EmbeddingService:
    """Build (once) and return the configured EmbeddingService."""
    global _provider
    if _provider is None:
        settings = get_settings()
        if settings.embedding_provider == "openai":
            from .openai import OpenAIEmbeddingProvider

            _provider = OpenAIEmbeddingProvider(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                model=settings.embedding_model,
                dimension=settings.embedding_dim,
            )
        else:
            from .local import LocalEmbeddingProvider

            _provider = LocalEmbeddingProvider(dimension=settings.local_embedding_dim)
    return EmbeddingService(_provider)
