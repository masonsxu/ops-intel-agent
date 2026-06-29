"""Offline embedding provider based on character n-gram hashing.

This is NOT a neural model, but it produces stable, semantically-meaningful
vectors: similar exception messages yield high cosine similarity because they
share character trigrams. It lets the entire RAG pipeline run with zero
external dependencies for local development and demos, and is more than
sufficient to exercise the retrieval/matching logic.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

import numpy as np

from .base import EmbeddingProvider

_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_]{1,}")


class LocalEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimension: int = 256) -> None:
        self._dim = int(dimension)

    @property
    def dimension(self) -> int:
        return self._dim

    def _vectorize(self, text: str) -> list[float]:
        if not text:
            return [0.0] * self._dim
        # Lowercase token stream plus the raw string for character coverage.
        tokens = _TOKEN_RE.findall(text.lower())
        # Build a feature bag: word-unigrams, word-bigrams, char-trigrams.
        feats: Counter[int] = Counter()
        for tok in tokens:
            feats[self._hash(tok)] += 1.0
            # sublinear damping so one repeated word doesn't dominate
            feats[self._hash(tok)] = 1.0 + math.log(feats[self._hash(tok)] + 1)
        for a, b in zip(tokens, tokens[1:], strict=False):
            feats[self._hash(f"{a}_{b}")] += 1.0
        padded = "^" + text.lower() + "$"
        for i in range(len(padded) - 2):
            feats[self._hash("c3:" + padded[i : i + 3])] += 1.0

        vec = np.zeros(self._dim, dtype=np.float32)
        for h, w in feats.items():
            vec[h % self._dim] += float(w)
        # L2 normalize; guard against zero vector.
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return vec.tolist()

    def _hash(self, s: str) -> int:
        # Deterministic 64-bit hash -> stable across processes/restarts.
        return int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "big")

    async def embed_text(self, text: str) -> list[float]:
        return self._vectorize(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self._vectorize(t) for t in texts]
