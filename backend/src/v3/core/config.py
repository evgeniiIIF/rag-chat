"""Настройки сервиса: единственное место чтения env.

Граница JSON/env -> pydantic v2 (rules/types.md). Значения по умолчанию повторяют
`.env.example` корневого проекта, чтобы v3 работал на том же `.env`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

RAGCHAT_DIR: Path = Path(__file__).resolve().parents[1]  # backend/src/v3


def _ancestor(path: Path, levels: int) -> Path | None:
    """Предок на `levels` уровней выше; в контейнере (/app) уровней меньше — None."""
    parents = path.parents
    return parents[levels] if len(parents) > levels else None


REPO_ROOT: Path | None = _ancestor(RAGCHAT_DIR, 2)  # корень монорепо, в образе его нет
DATA_DIR_DEFAULT: Path = REPO_ROOT / "backend" / "data" if REPO_ROOT is not None else Path("/data")
CHUNKS_DOC_DEFAULT: Path = (REPO_ROOT / "docs" / "chunks.md") if REPO_ROOT is not None else Path("/app/docs/chunks.md")


class Settings(BaseSettings):
    """Настройки, читаемые из env (префикс BACKEND_)."""

    model_config = SettingsConfigDict(env_prefix="BACKEND_", env_file=".env", extra="ignore")

    api_key: SecretStr
    base_url: str = "https://polza.ai/api/v1"
    llm_model: str = "deepseek/deepseek-v4.1-flash-1017"
    embedding_model: str = "qwen/qwen3-embedding-8b"

    data_dir: Path = DATA_DIR_DEFAULT
    chroma_dir: Path = RAGCHAT_DIR / ".chroma"
    artifacts_dir: Path = RAGCHAT_DIR / "artifacts"
    # читаемый снимок нарезки: пишется при сборке индекса, лежит рядом с документацией
    chunks_doc: Path = CHUNKS_DOC_DEFAULT

    retriever_k: int = Field(default=5, ge=1, le=10)
    score_threshold: float = Field(default=0.35, ge=0.0, le=1.0)

    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=800, ge=1, le=8192)
    log_level: str = "INFO"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Вернуть настройки (кэш на процесс)."""
    return Settings()  # type: ignore[call-arg]  # поля читаются из env, не из аргументов
