"""SafeLLM: обертка над OpenAI-совместимым LLM для RAGAS, которая не отправляет пустые строки."""

from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI
from ragas.llms.base import BaseRagasLLM
from ragas.run_config import RunConfig


class SafeLLM(BaseRagasLLM):
    """Обертка, которая отсекает пустые промпты перед отправкой в API."""

    def __init__(self, llm: ChatOpenAI) -> None:
        self.llm = llm

    def generate_text(self, prompt: Any, n: int = 1, temperature: float = 1e-8, stop: Any = None, callbacks: Any = None) -> Any:
        # Извлекаем текст промпта
        text = prompt.to_string() if hasattr(prompt, "to_string") else str(prompt)
        if not text or not text.strip():
            # Возвращаем заглушку вместо пустой строки
            from langchain_core.outputs import LLMResult, Generation
            return LLMResult(generations=[[Generation(text="Нет данных")]])
        # Если не пустой — отправляем в LLM
        return self.llm.generate([prompt], n=n, temperature=temperature, stop=stop, callbacks=callbacks)

    async def agenerate_text(self, prompt: Any, n: int = 1, temperature: float = 1e-8, stop: Any = None, callbacks: Any = None) -> Any:
        return self.generate_text(prompt, n, temperature, stop, callbacks)

    def is_finished(self, response: Any) -> bool:
        return True
