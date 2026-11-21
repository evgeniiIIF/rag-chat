"""Оценка качества ответов ragas по golden set (запускается вручную, не в make check).

Скрипт опрашивает уже поднятый сервис (`POST /api/chat`) и считает faithfulness /
answer_relevancy / context_precision по `backend/eval/golden_set.json`.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

V3_DIR = Path(__file__).resolve().parents[1]
GOLDEN_SET = V3_DIR.parents[1] / "eval" / "golden_set.json"
SERVICE_URL = os.getenv("BACKEND_V3_URL", "http://localhost:8000")
CHAT_PATH = "/api/chat"


def load_golden_set() -> list[dict[str, str]]:
    """Контрольные вопросы с эталонными ответами."""
    rows: list[dict[str, str]] = json.loads(GOLDEN_SET.read_text(encoding="utf-8"))
    return rows


def collect_answers() -> list[dict[str, object]]:
    """Ответы сервиса по каждому контрольному вопросу (с контекстом-источниками)."""
    import httpx

    samples: list[dict[str, object]] = []
    with httpx.Client(base_url=SERVICE_URL, timeout=60.0) as client:
        for row in load_golden_set():
            response = client.post(CHAT_PATH, json={"question": row["question"]})
            response.raise_for_status()
            payload = response.json()
            samples.append(
                {
                    "user_input": row["question"],
                    "response": payload["answer"],
                    "retrieved_contexts": [source["text"] for source in payload["sources"]] or [""],
                    "reference": row["ground_truth"],
                }
            )
    return samples


def evaluate(samples: list[dict[str, object]]) -> None:
    """Посчитать метрики ragas и напечатать их."""
    from ragas import EvaluationDataset
    from ragas import evaluate as ragas_evaluate
    from ragas.metrics import answer_relevancy, context_precision, faithfulness

    dataset = EvaluationDataset.from_list(samples)  # type: ignore[arg-type]
    result = ragas_evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy, context_precision],
    )
    print(result)  # it is a CLI script


def main() -> int:
    """Точка входа: собрать ответы и посчитать метрики."""
    samples = collect_answers()
    if not samples:
        print("golden set пуст", file=sys.stderr)
        return 1
    evaluate(samples)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
