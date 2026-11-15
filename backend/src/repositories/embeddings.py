"""Обёртка над OpenAIEmbeddings; SecretStr без .get_secret_value()."""

from __future__ import annotations

from langchain_openai import OpenAIEmbeddings

from ..core.config import Settings


class OpenAIEmbeddingsAdapter:
    def __init__(self, settings: Settings) -> None:
        self._embeddings = OpenAIEmbeddings(
            model=settings.embedding_model,
            api_key=settings.api_key.get_secret_value(),
            base_url=settings.base_url,
            check_embedding_ctx_length=False,
            tiktoken_enabled=False,
            allowed_special=set(),
            disallowed_special=set(),
        )

    def get(self) -> OpenAIEmbeddings:
        return self._embeddings
