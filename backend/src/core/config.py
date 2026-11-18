"""Единственный источник env для backend. pydantic-settings, fail-fast."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Схема env. Любой ключ вне схемы — ошибка валидации."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    api_key: SecretStr = Field(..., alias="API_KEY")
    base_url: str = Field("https://polza.ai/api/v1", alias="BASE_URL")
    embedding_model: str = Field("qwen/qwen3-embedding-8b", alias="EMBEDDING_MODEL")
    llm_model: str = Field("deepseek/deepseek-r1-distill-llama-70b", alias="LLM_MODEL")

    chroma_dir: str = Field("/app/chroma_db", alias="CHROMA_DIR")
    data_dir: str = Field("/app/data", alias="DATA_DIR")

    chunk_size: int = Field(500, ge=50, le=2000, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(100, ge=0, le=1000, alias="CHUNK_OVERLAP")
    retriever_k: int = Field(3, ge=1, le=10, alias="RETRIEVER_K")
    score_threshold: float = Field(0.35, ge=0.0, le=1.0, alias="SCORE_THRESHOLD")
    temperature: float = Field(0.0, ge=0.0, le=1.0, alias="TEMPERATURE")
    max_tokens: int = Field(500, ge=50, le=4000, alias="MAX_TOKENS")
    session_ttl_seconds: int = Field(86400, ge=60, le=604800, alias="SESSION_TTL_SECONDS")
    session_max_sessions: int = Field(1000, ge=1, le=100000, alias="SESSION_MAX_SESSIONS")
    session_max_turns: int = Field(30, ge=2, le=100, alias="SESSION_MAX_TURNS")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field("INFO", alias="LOG_LEVEL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Fail-fast: ошибки валидации env — с перечнем ключей."""
    try:
        return Settings()
    except ValidationError as exc:
        invalid = ", ".join(str(err["loc"][0]) for err in exc.errors())
        raise RuntimeError(f"Невалидные env-ключи: {invalid}") from exc
