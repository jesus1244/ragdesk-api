from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

EMBEDDING_DIMENSIONS = 768
_WEAK_SECRET_MARKERS = ("change-me", "secret", "password")


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"

    @property
    def is_deployed(self) -> bool:
        return self in {Environment.STAGING, Environment.PRODUCTION}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- app
    app_name: str = "RAGDesk API"
    environment: Environment = Environment.LOCAL
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:4200"]
    api_prefix: str = "/api/v1"
    expose_docs: bool = False  # only matters in deployed environments

    # --- infrastructure
    database_url: str = "postgresql+asyncpg://ragdesk:ragdesk@localhost:5435/ragdesk"
    database_pool_size: int = 10
    redis_url: str = "redis://localhost:6381/0"

    # --- auth
    jwt_secret: SecretStr = SecretStr("change-me-in-production-please-32-bytes-min")
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14

    # --- rate limiting (requests per minute, per client IP)
    rate_limit_auth_per_minute: int = 10
    rate_limit_upload_per_minute: int = 20
    rate_limit_chat_per_minute: int = 20

    # --- ingestion
    max_upload_mb: int = 20
    max_sources_per_bot: int = 50
    max_text_chars: int = 500_000
    chunk_target_chars: int = 1500
    url_fetch_timeout_seconds: float = 15.0
    url_fetch_max_mb: int = 5
    url_allow_private_hosts: bool = False  # True only for local development

    # --- retrieval
    retrieval_top_k: int = 6
    retrieval_candidates: int = 30
    retrieval_max_distance: float = 0.55  # cosine distance; larger means less similar

    # --- providers: "fake" runs offline and deterministically
    embedder: Literal["gemini", "fake"] = "fake"
    gemini_api_key: SecretStr | None = None
    gemini_embedding_model: str = "gemini-embedding-2"
    chat_model_provider: Literal["claude", "fake"] = "fake"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: Literal["low", "medium", "high"] = "low"
    chat_max_tokens: int = 1500

    @property
    def docs_enabled(self) -> bool:
        return not self.environment.is_deployed or self.expose_docs

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def url_fetch_max_bytes(self) -> int:
        return self.url_fetch_max_mb * 1024 * 1024

    @model_validator(mode="after")
    def _fail_fast_in_deployed_environments(self) -> "Settings":
        if not self.environment.is_deployed:
            return self
        problems: list[str] = []
        secret = self.jwt_secret.get_secret_value()
        if len(secret) < 32 or any(m in secret.lower() for m in _WEAK_SECRET_MARKERS):
            problems.append("JWT_SECRET must be a random string of at least 32 characters")
        if self.embedder == "gemini" and self.gemini_api_key is None:
            problems.append("GEMINI_API_KEY is required when EMBEDDER=gemini")
        if self.chat_model_provider == "claude" and self.anthropic_api_key is None:
            problems.append("ANTHROPIC_API_KEY is required when CHAT_MODEL_PROVIDER=claude")
        if self.url_allow_private_hosts:
            problems.append("URL_ALLOW_PRIVATE_HOSTS must be false")
        if problems:
            raise ValueError("Invalid production configuration: " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
