import asyncio

import numpy as np

from ops_intel_agent.services.embeddings import get_embedding_service


def test_similar_logs_have_high_similarity():
    svc = get_embedding_service()
    a = asyncio.run(svc.embed("JedisConnectionException redis connection refused timeout"))
    b = asyncio.run(
        svc.embed("JedisConnectionException Failed connecting to redis connection timed out")
    )
    sim = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    assert sim > 0.7


def test_unrelated_logs_have_lower_similarity():
    svc = get_embedding_service()
    a = asyncio.run(svc.embed("redis connection refused timeout"))
    b = asyncio.run(svc.embed("certificate expired ssl handshake failed"))
    sim = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    assert sim < 0.6


def test_zero_dim_vector_on_empty():
    svc = get_embedding_service()
    v = asyncio.run(svc.embed(""))
    assert all(x == 0.0 for x in v)
