# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Ops Intel Agent — a FastAPI service that triages server anomalies with **RAG + LLM**: it turns raw error logs into (a) plain-language notifications for end users and (b) technical playbooks for SREs, then deposits resolved incidents back into a vector knowledge base so the system "gets smarter over time." Python 3.11+, managed with `uv`.

## Commands

```bash
make install          # uv sync — runtime deps only (offline-capable default)
make dev              # uv sync --extra dev (adds pytest, ruff, mypy, respx)
make prod             # uv sync --extra prod (adds openai, asyncpg, pgvector, alembic)
make run              # uvicorn ops_intel_agent.main:app --reload --port 8000
make seed             # seed 3 demo incidents into the knowledge base + vector store
make demo             # seed + fire 3 sample alerts (run server in another terminal first)
make test             # uv run pytest -q  (fully offline, ~0.2s)
make lint             # ruff check + ruff format --check + mypy (mypy is advisory: `|| true`)
make format           # ruff format + ruff check --fix
```

Run a single test (pytest is configured with `asyncio_mode = "auto"`):

```bash
uv run pytest tests/test_pipeline.py -q
uv run pytest tests/test_pipeline.py::test_known_incident_matches -q
```

There are no Cursor/Copilot rules files; the conventions below come from the code, `pyproject.toml`, and `Makefile`.

## Architecture

### The defining design choice: pluggable backends behind abstract interfaces

Every external dependency is an ABC in `ops_intel_agent/services/<name>/base.py` with two interchangeable implementations. **The same codebase runs fully offline (no API keys, no DB) for local dev/demos, or against production services by flipping `OIA_*` env vars — business logic never changes.**

| Concern | Interface (`services/.../base.py`) | Offline default | Prod impl |
| --- | --- | --- | --- |
| Embeddings | `EmbeddingProvider` | `LocalEmbeddingProvider` (char n-gram hash, **256-dim**) | `OpenAIEmbeddingProvider` (**1536-dim**) |
| LLM | `LLMProvider` | `LocalLLMProvider` (template) | `OpenAILLMProvider` |
| Vectors | `VectorStore` | `MemoryVectorStore` (numpy cosine, JSON-persisted) | `PgVectorStore` |
| Notify | `Notifier` | `ConsoleNotifier` | `WeChatNotifier` / `DingTalkNotifier` |
| Actions | `ActionRegistry` | 5 builtin no-op handlers | wire to Ansible/kubectl |

Each module exposes a module-level singleton (`_provider`, `_store`, `_notifier`, `_registry`) and a `get_*()` factory that reads `Settings` to pick the implementation. **These singletons and `get_settings()` (which is `@lru_cache(maxsize=1)`) are process-global** — see the testing gotcha below.

### The triage pipeline (`core/pipeline.py`) is the orchestrator

`TriagePipeline.process()` is the single end-to-end path; every API alert flows through it:

```
raw log → parse_log (extractors/log_parser) → embed canonical_text
       → VectorStore.search("knowledge", vec, k) → threshold decision
       → (matched) ActionRegistry.suggest_for(...) + bump occurrence_count
       → LLMService.triage(ctx) → DiagnosticReport
       → persist ErrorAlert + commit → Notifier.send(NotificationPayload)
```

`match_status` is `"matched"` when `best_similarity >= OIA_SIMILARITY_THRESHOLD` (default 0.78), else `"new_incident"`. The vector namespace `"knowledge"` is the constant `KNOWLEDGE_NS` in `core/pipeline.py` — reuse it wherever you touch knowledge vectors.

### The knowledge closed-loop (`core/deposition.py`)

`POST /knowledge/depositions` takes an engineer's free-form resolution for a `new_incident` alert, asks the LLM to structure it (`build_knowledge`), writes a row to `ErrorKnowledgeBase` + its embedding to the vector store, and flips the originating alert to `status=resolved` / `match_status=deposited`. The next identical alert then matches at high similarity with no human in the loop.

### Critical invariant: the Markdown contract

The LLM (local **and** OpenAI) must emit output with **fixed Chinese section headers** (`📢 【当前问题大白话翻译】`, `🛠️ 【您可以采取的行动】`, `👨‍💻 【技术排查参考（供工程师）】` for triage; `【错误类型】`/`【标题】`/`【根因】`/`【用户指引】`/`【工程师指引】` for deposition). The regex parsers in `prompts/templates.py` (`parse_triage_markdown`, `parse_deposition_markdown`) depend on these exact headers. **`services/llm/local.py` must produce output that parses with the same regexes as the real LLM** — if you edit the prompt headers, update both the parser and the local provider, or the offline path silently degrades.

`prompts/templates.py` owns prompt assembly *and* parsing, kept out of the pipeline on purpose. The `LLMService` in `services/llm/base.py` is the thin wrapper that pairs them.

### Storage

- **Relational** (`db/`): SQLAlchemy 2.0 async. Default SQLite (`ops_intel_agent.db`, `aiosqlite`); prod = `postgresql+asyncpg`. `init_db()` runs `Base.metadata.create_all` on startup — there is **no Alembic migration flow in the default path** (Alembic is a `prod` extra for real deployments). Sessions come from `db/session.py`; the `get_db` dependency rolls back on exception.
- **Vectors**: `MemoryVectorStore` persists to `ops_intel_agent.vectors.json` (path = `OIA_MEMORY_VECTOR_PATH`), keyed by `(namespace, id)` so seeding in one process survives into the server process. The relational `ErrorKnowledgeBase` row deliberately does **not** store its embedding — that lives only in the vector store.

### Alert aggregation (`core/aggregator.py`)

Sliding-window clustering collapses a burst of near-duplicate alerts (e.g. 10 services failing when one DB wobbles) into a single notification. It's single-process in-memory, started as a background flusher task in `main.py`'s `lifespan`. Controlled by `OIA_ENABLE_AGGREGATION`, `OIA_AGGREGATION_WINDOW_SECONDS`, `OIA_AGGREGATION_MIN_CLUSTER_SIZE`. For multi-replica deploy this dict must become Redis.

### App wiring (`main.py`)

`create_app()` mounts four routers (`health`, `alerts`, `knowledge`, `actions`) and CORS. The `lifespan` context manager configures logging, runs `init_db()`, and starts the aggregator flusher if aggregation is enabled; on shutdown it cancels the flusher and disposes the engine.

## Testing conventions (read before writing tests)

- All tests run **fully offline**: `tests/conftest.py` force-sets `OIA_EMBEDDING_PROVIDER=local`, `OIA_LLM_PROVIDER=local`, `OIA_VECTOR_STORE=memory`, `OIA_NOTIFIER_PROVIDER=console` before any app import.
- The `isolated_env` autouse fixture gives each test a private `OIA_MEMORY_VECTOR_PATH` under `tmp_path` **and** calls `_reset_singletons()` to clear the cached service singletons + `get_settings` before and after every test. **If you add a new cached singleton, register it in `_reset_singletons()`** or tests will leak state across each other.
- `db_session` fixture = fresh in-memory SQLite per test. API tests in `test_api.py` override the `db_session` FastAPI dependency to point at this isolated session.
- To change a setting mid-test, `monkeypatch.setenv(...)` then `get_settings.cache_clear()` before constructing the pipeline/service (see `test_pipeline.py`).

## Lint / style specifics

- Ruff line-length **100**, target `py311`, rules `E,F,I,B,UP,N,SIM,C4,RET`.
- `api/*.py` ignores `B008` (FastAPI `Depends()` in argument defaults is idiomatic). `tests/*.py` allows `E501,N802,S101`; `scripts/*.py` allows `E501,T201` (print statements).
- `mypy --strict` is on but the `make lint` target tolerates its failure (`|| true`) — treat it as advisory.
