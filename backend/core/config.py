"""
ARA-1 Core Configuration
Pydantic-based settings loaded from environment variables / .env file.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, AnyUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────
    app_name: str = "ARA-1"
    app_env: str = "development"
    app_debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    secret_key: str = Field(default="change-me-in-production")
    allowed_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"]
    )

    # ── OpenAI ───────────────────────────────────────────────────
    openai_api_key: str = Field(default="")
    openai_base_url: str = Field(default="")
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-large"
    openai_max_tokens: int = 4096
    openai_temperature: float = 0.1

    # ── PostgreSQL ───────────────────────────────────────────────
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "ara1"
    postgres_user: str = "ara1_user"
    postgres_password: str = "ara1_secure_password"
    database_url: str = Field(default="")

    @property
    def async_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ── Redis ────────────────────────────────────────────────────
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0
    redis_url: str = Field(default="")
    redis_ttl_seconds: int = 3600

    @property
    def redis_connection_url(self) -> str:
        if self.redis_url:
            return self.redis_url
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # ── Qdrant ───────────────────────────────────────────────────
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_api_key: str = ""
    qdrant_collection_name: str = "ara1_documents"
    qdrant_vector_size: int = 3072  # text-embedding-3-large

    # ── Financial APIs ────────────────────────────────────────────
    alpha_vantage_api_key: str = ""
    news_api_key: str = ""
    sec_api_key: str = ""

    # ── Agent Configuration ───────────────────────────────────────
    max_research_iterations: int = 5
    max_tool_calls_per_agent: int = 10
    agent_timeout_seconds: int = 120
    planner_max_subtasks: int = 10

    # ── RAG Configuration ─────────────────────────────────────────
    rag_top_k: int = 20
    rag_rerank_top_k: int = 5
    rag_chunk_size: int = 1000
    rag_chunk_overlap: int = 200

    # ── Retry Configuration ───────────────────────────────────────
    max_retries: int = 3
    retry_min_wait: float = 1.0
    retry_max_wait: float = 60.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: int = 60

    # ── Logging ───────────────────────────────────────────────────
    log_level: str = "INFO"
    log_format: str = "json"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

if settings.openai_base_url:
    import os
    os.environ["OPENAI_BASE_URL"] = settings.openai_base_url
