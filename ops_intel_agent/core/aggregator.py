"""Sliding-window alert aggregation.

When a database wobbles, ten upstream services may each emit a *different*
error within seconds. We don't want ten bot messages. This module clusters
alerts whose canonical embeddings are near-duplicates inside a time window and
emits a single aggregated notification instead.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

import numpy as np

from ..logging import get_logger
from ..schemas.alert import AlertCreate
from ..schemas.report import NotificationPayload
from ..services.embeddings import get_embedding_service
from ..services.notifier import get_notifier

log = get_logger(__name__)


@dataclass(slots=True)
class _Pending:
    payload: AlertCreate
    embedding: list[float]
    first_seen: float
    count: int = 1
    services: set[str] = field(default_factory=set)
    raw_examples: list[str] = field(default_factory=list)


class AlertAggregator:
    """Buckets similar alerts within a window; flushes single notifications.

    NOTE: for clarity this is a single-process in-memory implementation. For a
    multi-replica deployment, swap the dict for a Redis-backed structure.
    """

    def __init__(
        self,
        window_seconds: int = 300,
        min_cluster_size: int = 2,
        similarity_threshold: float = 0.88,
    ) -> None:
        self.window = window_seconds
        self.min_size = min_cluster_size
        self.threshold = similarity_threshold
        self._buckets: dict[str, _Pending] = {}  # cluster_key -> pending
        self._embeddings = get_embedding_service()
        self._notifier = get_notifier()
        self._lock = asyncio.Lock()

    async def offer(self, payload: AlertCreate) -> str | None:
        """Returns the cluster_key if the alert was absorbed into a cluster."""
        vec = await self._embeddings.embed(_canonical(payload.raw_log))
        key = self._find_cluster(vec)
        async with self._lock:
            if key is None:
                key = f"c{int(time.time() * 1000)}"
                self._buckets[key] = _Pending(
                    payload=payload, embedding=vec, first_seen=time.time()
                )
                if payload.service:
                    self._buckets[key].services.add(payload.service)
                self._buckets[key].raw_examples.append(payload.raw_log[:200])
                return None  # not yet a cluster
            bucket = self._buckets[key]
            bucket.count += 1
            if payload.service:
                bucket.services.add(payload.service)
            bucket.raw_examples.append(payload.raw_log[:200])
            return key

    def _find_cluster(self, vec: list[float]) -> str | None:
        q = np.asarray(vec, dtype=np.float32)
        qn = np.linalg.norm(q)
        if qn == 0:
            return None
        q = q / qn
        now = time.time()
        best_key, best_score = None, 0.0
        for key, bucket in list(self._buckets.items()):
            if now - bucket.first_seen > self.window:
                continue
            v = np.asarray(bucket.embedding, dtype=np.float32)
            vn = np.linalg.norm(v)
            if vn == 0:
                continue
            sim = float((v / vn) @ q)
            if sim > best_score:
                best_score, best_key = sim, key
        return best_key if best_score >= self.threshold else None

    async def flush_due(self) -> list[NotificationPayload]:
        """Flush clusters whose window has elapsed, returning notifications."""
        now = time.time()
        sent: list[NotificationPayload] = []
        async with self._lock:
            due = [k for k, b in self._buckets.items() if now - b.first_seen >= self.window]
        for key in due:
            async with self._lock:
                bucket = self._buckets.pop(key, None)
            if bucket is None:
                continue
            if bucket.count < self.min_size:
                continue  # not a real cluster; the pipeline already notified
            services = ", ".join(sorted(bucket.services)) or "多个服务"
            title = f"📢 聚合告警 · {bucket.count} 条相似异常 · {services}"
            markdown = (
                f"在过去 {self.window // 60} 分钟内检测到 **{bucket.count}** 条高度相似的异常，"
                f"涉及服务：**{services}**。\n"
                "初步判断为同一根因引起（例如：共享的数据库/缓存抖动），正在合并处理。\n\n"
                "**示例日志：**\n" + "\n".join(f"- `{e}`" for e in bucket.raw_examples[:3])
            )
            payload = NotificationPayload(title=title, markdown=markdown)
            try:
                await self._notifier.send(payload)
                sent.append(payload)
                log.info("aggregator.flush", cluster=key, count=bucket.count)
            except Exception as exc:  # noqa: BLE001
                log.error("aggregator.flush.failed", error=str(exc))
        return sent

    def start_flusher(self, interval: float = 30.0) -> asyncio.Task:
        async def _loop():
            while True:
                await asyncio.sleep(interval)
                try:
                    await self.flush_due()
                except Exception as exc:  # noqa: BLE001
                    log.error("aggregator.loop.error", error=str(exc))

        return asyncio.create_task(_loop(), name="aggregator-flush")


def _canonical(raw: str) -> str:
    from ..extractors import parse_log

    return parse_log(raw).canonical_text
