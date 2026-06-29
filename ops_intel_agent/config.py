"""Centralized configuration via pydantic-settings.

All backends are pluggable through environment variables so the same codebase
runs fully offline (mock providers + in-memory store) for local development and
against real services (OpenAI, PostgreSQL+pgvector, WeChat Work) in production.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="OIA_",
        extra="ignore",
        case_sensitive=False,
    )

    # --- General -----------------------------------------------------------
    app_name: str = "ops-intel-agent"
    environment: Literal["dev", "staging", "prod"] = "dev"
    log_level: str = "INFO"

    # --- Backend selection -------------------------------------------------
    embedding_provider: Literal["openai", "local"] = "local"
    llm_provider: Literal["openai", "local"] = "local"
    # Chroma is the default local/test store: embedded, offline, disk-persisted.
    # `memory` = the in-process numpy/JSON store (used by the test suite).
    # `pgvector` = production PostgreSQL + pgvector.
    vector_store: Literal["pgvector", "memory", "chroma"] = "chroma"
    notifier_provider: Literal["wechat", "dingtalk", "console"] = "console"

    # --- Embedding / LLM (OpenAI) -----------------------------------------
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.2

    # --- Local (offline) providers ----------------------------------------
    # Smaller dimension keeps the in-memory/numpy store cheap; semantic
    # structure comes from character n-gram hashing.
    local_embedding_dim: int = 256

    # --- Vector store ------------------------------------------------------
    database_url: str = "sqlite+aiosqlite:///./ops_intel_agent.db"
    # When vector_store == "pgvector" this should be a postgres+asyncpg URL.
    pg_connection_string: str = "postgresql+asyncpg://ops:ops@localhost:5432/ops"
    # Where the in-memory store persists its vectors so offline mode survives
    # process restarts (seed in one process, serve in another).
    memory_vector_path: str = "ops_intel_agent.vectors.json"
    # Where the embedded Chroma store persists its data (SQLite + Parquet).
    chroma_path: str = "./chroma_db"

    # --- Retrieval ---------------------------------------------------------
    similarity_top_k: int = 3
    # Cosine similarity threshold above which a historical case is considered
    # a confident match. Below it the alert is flagged as "new incident".
    similarity_threshold: float = 0.78
    # Aggregation window (seconds) used to collapse a burst of similar alerts
    # into a single notification.
    aggregation_window_seconds: int = 300
    aggregation_min_cluster_size: int = 2

    # --- Notification ------------------------------------------------------
    wechat_webhook: str | None = None
    dingtalk_webhook: str | None = None
    dingtalk_secret: str | None = None
    notify_on_new_incident: bool = True
    notify_action_buttons: bool = True

    # --- Pipeline ----------------------------------------------------------
    enable_action_suggestions: bool = True
    enable_aggregation: bool = True
    # Confidence above which the bot suggests a one-click remediation button.
    action_confidence_threshold: float = 0.85

    # --- API ---------------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    # Directory of the built frontend SPA. If it exists at startup we mount it
    # at "/" so FastAPI serves the UI alongside the API (single-origin deploy).
    frontend_dir: str = "frontend/dist"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
