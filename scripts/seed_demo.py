"""Seed the knowledge base with realistic demo incidents.

Prefer running this **after** starting the API (`make run`): when the server is
reachable the script seeds via `POST /knowledge`, which keeps every vector write
inside the server process — important for the embedded Chroma store, which does
not see direct cross-process writes to its files. If the server is not running,
the script falls back to writing the DB/vector store directly (offline mode).
"""

from __future__ import annotations

import asyncio

import httpx

from ops_intel_agent.config import get_settings
from ops_intel_agent.core.pipeline import KNOWLEDGE_NS
from ops_intel_agent.db.session import SessionLocal, init_db
from ops_intel_agent.extractors import parse_log
from ops_intel_agent.models import ErrorKnowledgeBase
from ops_intel_agent.services.embeddings import get_embedding_service
from ops_intel_agent.services.vectorstore import VectorRecord, get_vector_store

DEMO = [
    {
        "error_type": "Redis 连接超时",
        "title": "Redis 连接超时导致登录态丢失",
        "raw_log_sample": (
            "ERROR 2026-06-29 10:23:11 service=auth host=app-01 "
            "JedisConnectionException: Failed connecting to redis://10.0.1.2:6379 "
            "Connection refused (connection timed out)"
        ),
        "root_cause": "Redis 实例 10.0.1.2 因内存 OOM 被 OOM-Killer 杀死，导致所有依赖会话缓存的服务连接被拒。",
        "user_guide": "目前登录功能暂时不可用，原因是后台缓存服务短暂断开，正在自动恢复，请 1-2 分钟后重试。",
        "engineer_guide": (
            "1. 检查 10.0.1.2 上 redis 容器是否被 OOM-Killed (dmesg | grep -i oom)；\n"
            "2. redis-cli INFO memory 查看used_memory与maxmemory；\n"
            "3. 临时清理缓存或扩容 maxmemory；\n"
            "4. 重启 redis：kubectl rollout restart deploy/redis。\n"
            "5. 如频繁 OOM，评估扩容或开启逐出策略 allkeys-lru。"
        ),
        "tags": ["redis", "cache", "oom", "auth"],
    },
    {
        "error_type": "MySQL 连接池耗尽",
        "title": "支付服务数据库连接池耗尽",
        "raw_log_sample": (
            "FATAL service=payments host=pay-02 ip=10.0.2.5 "
            "HikariPool-1 - Connection is not available, request timed out after 30000ms "
            "(max_pool=50 active=50)"
        ),
        "root_cause": "上游慢查询持有连接过久，HikariCP 连接池被打满，新请求全部排队超时。",
        "user_guide": "支付与下单功能暂时无法使用，正在紧急处理，请稍后重试。",
        "engineer_guide": (
            "1. SHOW FULL PROCESSLIST 找出长事务/慢查询并 kill；\n"
            "2. 检查是否有未提交事务或锁等待 (SELECT * FROM information_schema.INNODB_TRX)；\n"
            "3. 临时扩容连接池 maximumPoolSize；\n"
            "4. 重启 payments 服务释放连接；\n"
            "5. 事后给慢查询加索引并设置 statement_timeout。"
        ),
        "tags": ["mysql", "db", "pool", "payments"],
    },
    {
        "error_type": "JVM 内存溢出",
        "title": "网关服务 JVM Old 区溢出",
        "raw_log_sample": (
            "ERROR service=gateway host=gw-01 java.lang.OutOfMemoryError: Java heap space\n"
            "    at com.example.gateway.router.RequestRouter.dispatch(RequestRouter.java:88)\n"
            "    at java.base/java.util.concurrent.ThreadPoolExecutor.runWorker(ThreadPoolExecutor.java:1128)"
        ),
        "root_cause": "网关缓存了一个无界 Map 导致 Old 区持续增长，最终 Full GC 无法回收，触发 OOM。",
        "user_guide": "部分接口访问变慢或失败，系统正在自动重启相关模块，期间有几秒不可用。",
        "engineer_guide": (
            "1. 确认是否发生 Full GC 风暴 (jstat -gcutil)；\n"
            "2. 导出堆dump: jmap -dump:format=b,file=heap.hprof <pid>；\n"
            "3. 重启 gateway：kubectl rollout restart deploy/gateway；\n"
            "4. 调大 -Xmx；定位无界缓存并加 LRU/Size 上限；\n"
            "5. 配置 -XX:+HeapDumpOnOutOfMemoryError 以便下次自动留存现场。"
        ),
        "tags": ["jvm", "oom", "heap", "gateway"],
    },
]


def _api_base() -> str:
    settings = get_settings()
    host = "127.0.0.1" if settings.api_host in ("0.0.0.0", "") else settings.api_host
    return f"http://{host}:{settings.api_port}"


async def _seed_via_api(base: str) -> int:
    """Seed through the running API (keeps vector writes in-process)."""
    seeded = 0
    async with httpx.AsyncClient(base_url=base, timeout=10.0) as client:
        for item in DEMO:
            resp = await client.post("/knowledge", json={**item, "source": "seed:demo"})
            resp.raise_for_status()
            kb = resp.json()
            print(f"  ✓ seeded (via API) #{kb['id']}: {kb['title']}")  # noqa: T201
            seeded += 1
    return seeded


async def _seed_directly() -> int:
    """Offline fallback: write the DB and vector store from this process."""
    await init_db()
    embeddings = get_embedding_service()
    store = get_vector_store()
    async with SessionLocal() as session:
        for item in DEMO:
            kb = ErrorKnowledgeBase(
                error_type=item["error_type"],
                title=item["title"],
                raw_log_sample=item["raw_log_sample"],
                root_cause=item["root_cause"],
                user_guide=item["user_guide"],
                engineer_guide=item["engineer_guide"],
                source="seed:demo",
                tags=",".join(item["tags"]),
                confidence=1.0,
            )
            session.add(kb)
            await session.flush()
            vec = await embeddings.embed(parse_log(item["raw_log_sample"]).canonical_text)
            await store.upsert(
                VectorRecord(
                    namespace=KNOWLEDGE_NS, id=kb.id, text=item["raw_log_sample"], embedding=vec
                )
            )
            print(f"  ✓ seeded #{kb.id}: {kb.title}")  # noqa: T201
        await session.commit()
    return await store.count(KNOWLEDGE_NS)


async def main() -> None:
    settings = get_settings()
    base = _api_base()
    # Detect a running server (short timeout). If up, seed through it so the
    # embedded Chroma client in the server process owns every write.
    server_up = False
    try:
        async with httpx.AsyncClient(base_url=base, timeout=1.5) as client:
            server_up = (await client.get("/ready")).status_code == 200
    except Exception:  # noqa: BLE001
        server_up = False

    if server_up:
        print(f"Detected API at {base} — seeding via HTTP POST /knowledge …")  # noqa: T201
        n = await _seed_via_api(base)
    else:
        print("API not reachable — seeding the DB/vector store directly …")  # noqa: T201
        n = await _seed_directly()

    print(f"\nDone. {n} vectors in 'knowledge' namespace.")  # noqa: T201
    if settings.vector_store == "pgvector" and settings.embedding_provider != "openai":
        print("(note: pgvector dim must match provider dim — see OIA_EMBEDDING_DIM)")  # noqa: T201


if __name__ == "__main__":
    asyncio.run(main())
