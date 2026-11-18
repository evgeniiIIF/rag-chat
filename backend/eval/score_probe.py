"""Замер скоров гибридного поиска по golden_set (цепочка chat_v2, шаг S08).

Нужен, чтобы задать SCORE_THRESHOLD числом, а не на глазок: печатает top_score каждого
вопроса золотого набора и рекомендованный порог (середина между «попал» и «промах»).

Запуск (нужен собранный индекс и API-ключ в backend/.env):
    make probe            # из backend/
    uv run python -m eval.score_probe
"""

from __future__ import annotations

import json
from pathlib import Path

from src.core.config import Settings, get_settings
from src.main import _index_data
from src.repositories.embeddings import OpenAIEmbeddingsAdapter
from src.repositories.hybrid_retriever import HybridRetriever, top_score
from src.repositories.vector_store import VectorStoreRepository

GOLDEN = Path(__file__).parent / "golden_set.json"
# Вопросы, которых в базе нет: по ним порог обязан отсечь выдачу.
NEGATIVE_QUESTIONS: tuple[str, ...] = (
    "про гипопотамов",
    "какой прогноз на матч сегодня",
    "как приготовить борщ",
)


def main() -> int:
    # эмулируем окружение, потому что SCORE_THRESHOLD и другие настройки не требуют API_KEY
    settings = Settings(API_KEY="dummy", SCORE_THRESHOLD=0.35, RETRIEVER_K=4)
    embeddings = OpenAIEmbeddingsAdapter(settings).get()
    store = VectorStoreRepository(settings, embeddings=embeddings).load()
    chunks, _ = _index_data()
    retriever = HybridRetriever(store, chunks)
    k = settings.retriever_k

    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    positives: list[float] = []
    print(f"ПОЗИТИВНЫЕ (вопросы, накрытые базой), k={k}, порог сейчас={settings.score_threshold}")
    for item in golden:
        question = str(item["question"])
        hits = retriever.search(question, k)
        score = top_score(hits)
        positives.append(score)
        flag = "OK " if score >= settings.score_threshold else "МИМО"
        print(f"  [{flag}] {score:.3f}  {question}")

    negatives: list[float] = []
    print("\nНЕГАТИВНЫЕ (этого нет в базе — должно отсекаться)")
    for question in NEGATIVE_QUESTIONS:
        hits = retriever.search(question, k)
        score = top_score(hits)
        negatives.append(score)
        flag = "МИМО" if score < settings.score_threshold else "ТЕЧЁТ"
        print(f"  [{flag}] {score:.3f}  {question}")

    if positives and negatives:
        floor, ceiling = min(positives), max(negatives)
        print(f"\nmin позитивных = {floor:.3f}, max негативных = {ceiling:.3f}")
        if ceiling < floor:
            print(f"рекомендация: SCORE_THRESHOLD={((floor + ceiling) / 2):.2f}")
        else:
            print("рекомендация: порога достаточно не выйдет — позитивные и негативные пересекаются,")
            print("              решать должен вердикт модели (NO_ANSWER), порог ставить ниже min позитивных")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
