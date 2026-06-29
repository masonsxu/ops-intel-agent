"""Fire a sample alert against the running API to see end-to-end triage.

Talks to the HTTP API so it exercises the real FastAPI path. Falls back to
calling the pipeline directly if the server isn't up.
"""

from __future__ import annotations

import asyncio
import sys

import httpx

ALERTS = [
    {
        "service": "auth",
        "server_ip": "10.0.1.9",
        "host": "app-09",
        "severity": "critical",
        "raw_log": (
            "CRITICAL service=auth host=app-09 JedisConnectionException: "
            "Failed connecting to redis://10.0.1.2:6379 "
            "Connection refused (connection timed out after 5000ms)"
        ),
    },
    {
        "service": "orders",
        "server_ip": "10.0.2.7",
        "host": "ord-07",
        "severity": "error",
        "raw_log": (
            "ERROR service=orders HikariPool-1 - Connection is not available, "
            "request timed out after 30000ms. max_pool=50 active=50 idle=0"
        ),
    },
    {
        "service": "recommend",
        "server_ip": "10.0.5.2",
        "host": "rec-02",
        "severity": "error",
        "raw_log": (
            "ERROR something we have never seen before: GPU memory fragmentation "
            "in inference-engine v3.2, tensor cache corrupted at layer 47"
        ),
    },
]

API = "http://127.0.0.1:8000"


async def via_api() -> None:
    async with httpx.AsyncClient(timeout=30) as client:
        for a in ALERTS:
            print(f"\n>>> firing alert: {a['service']} ...")  # noqa: T201
            r = await client.post(f"{API}/alerts", json=a)
            print(f"    HTTP {r.status_code}")  # noqa: T201
            data = r.json()
            print(
                f"    match_status={data.get('match_status')} "  # noqa: T201
                f"sim={data.get('similarity_score')}"
            )
            rep = data.get("report") or {}
            print("    --- report ---")  # noqa: T201
            print("    " + (rep.get("plain_language") or "").replace("\n", "\n    "))  # noqa: T201


async def via_pipeline() -> None:
    from ops_intel_agent.config import get_settings
    from ops_intel_agent.core.pipeline import TriagePipeline
    from ops_intel_agent.db.session import SessionLocal, init_db
    from ops_intel_agent.schemas.alert import AlertCreate

    await init_db()
    pipeline = TriagePipeline(get_settings())
    async with SessionLocal() as session:
        for a in ALERTS:
            print(f"\n>>> firing alert: {a['service']} ...")  # noqa: T201
            res = await pipeline.process(session, AlertCreate(**a))
            print(  # noqa: T201
                f"    match_status={res.alert.match_status} sim={res.alert.similarity_score:.3f}"
            )
            print("    " + res.report.plain_language.replace("\n", "\n    "))  # noqa: T201


async def _api_alive() -> bool:
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            r = await client.get(f"{API}/health")
            return r.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
        return False


async def main() -> None:
    if await _api_alive():
        await via_api()
    else:
        print("(API not reachable — running pipeline directly in-process)", file=sys.stderr)  # noqa: T201
        await via_pipeline()


if __name__ == "__main__":
    asyncio.run(main())
