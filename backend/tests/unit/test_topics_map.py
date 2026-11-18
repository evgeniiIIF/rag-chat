"""Unit: TopicsMap (цепочка chat_v2, узел 08). Fake LLM-порт, сети нет."""

from __future__ import annotations

from src.models.chunk import Chunk, ParagraphSpan
from src.services.topics_map import TopicsMap, parse_topics


class _FakeLLM:
    def __init__(self, response: str = "", raises: bool = False) -> None:
        self.response = response
        self.raises = raises
        self.calls = 0
        self.last_user = ""

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        self.last_user = user
        if self.raises:
            raise RuntimeError("LLM недоступен")
        return self.response


def _corpus(*texts: str) -> list[Chunk]:
    return [Chunk(source="КЦ.docx", text=t, span=ParagraphSpan(start=i + 1, end=i + 1)) for i, t in enumerate(texts)]


def test_of_returns_model_topics_lowercase() -> None:
    llm = _FakeLLM('["списание долгов", "стоимость услуг", "регионы работы"]')
    topics = TopicsMap(llm).of(_corpus("берем в процедуру только с суммой от 350к"))
    assert topics.lines == ("списание долгов", "стоимость услуг", "регионы работы")
    assert llm.calls == 1


def test_of_caches_by_corpus_text() -> None:
    llm = _FakeLLM('["a"]')
    m = TopicsMap(llm)
    corpus = _corpus("x", "y")
    m.of(corpus)
    m.of(corpus)
    assert llm.calls == 1
    m.of(_corpus("другой текст"))
    assert llm.calls == 2


def test_cache_key_separates_index_versions() -> None:
    llm = _FakeLLM('["a"]')
    m = TopicsMap(llm)
    corpus = _corpus("x")
    m.of(corpus, cache_key="v1")
    m.of(corpus, cache_key="v2")
    assert llm.calls == 2


def test_empty_corpus_skips_llm() -> None:
    llm = _FakeLLM('["a"]')
    assert TopicsMap(llm).of([]).is_empty()
    assert llm.calls == 0


def test_llm_failure_degrades_to_empty_topics() -> None:
    topics = TopicsMap(_FakeLLM(raises=True)).of(_corpus("x"))
    assert topics.is_empty()


def test_prompt_contains_corpus_text() -> None:
    llm = _FakeLLM("[]")
    TopicsMap(llm).of(_corpus("63 субъекта РФ"))
    assert "63 субъекта РФ" in llm.last_user


def test_parse_topics_falls_back_to_plain_lines() -> None:
    raw = "1. Списание долгов\n- Стоимость\nприставы и коллекторы"
    assert parse_topics(raw) == ("списание долгов", "стоимость", "приставы и коллекторы")


def test_parse_topics_caps_count() -> None:
    raw = "[" + ",".join(f'"тема {i}"' for i in range(60)) + "]"
    assert len(parse_topics(raw)) == 25
