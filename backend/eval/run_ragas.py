import json
import os
import urllib.request
from pathlib import Path

from ragas import evaluate, EvaluationDataset, SingleTurnSample
from ragas.llms import llm_factory
from ragas.metrics import Faithfulness
from ragas.run_config import RunConfig

API_URL = "http://localhost:8081/api/chat"
GOLDEN = Path(__file__).parent / "golden_set.json"

def call_api(question: str) -> dict:
    data = json.dumps({"question": question}).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))

def main():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    samples = []

    print("Прогон золотого набора...")
    for item in golden:
        q = item["question"]
        print(f"  ❓ {q}")
        try:
            resp = call_api(q)
            ans = resp.get("answer", "Не знаю")
            sources = resp.get("sources", [])
            # ВАЖНО: берем полный текст чанка, а не snippet
            # (в API sources содержит только snippet, но мы можем взять его целиком)
            ctx = [s.get("text", "").strip() for s in sources if s.get("text", "").strip()]
            if not ctx:
                ctx = ["Нет контекста"]
        except Exception as e:
            print(f"    ⚠️ Ошибка: {e}")
            ans, ctx = "Не знаю", ["Нет контекста"]

        ans = ans.strip() if ans and ans.strip() else "Не знаю"

        samples.append(SingleTurnSample(
            user_input=q,
            response=ans,
            retrieved_contexts=ctx,
            reference=item["ground_truth"],
        ))

    dataset = EvaluationDataset(samples=samples)

    base_url = os.environ["OPENAI_BASE_URL"]
    llm = llm_factory("deepseek/deepseek-v3.2", base_url=base_url)

    run_config = RunConfig(max_workers=2, timeout=300, max_retries=5)

    print("\nОценка RAGAS (Faithfulness)...")
    result = evaluate(
        dataset=dataset,
        metrics=[Faithfulness()],
        llm=llm,
        run_config=run_config,
        raise_exceptions=False,
    )

    print("\n=== РЕЗУЛЬТАТЫ ===")
    print(result)
    # ФИКС: result.scores в 0.2.14 — это список словарей (по одному на sample)
    scores = result.scores
    if isinstance(scores, list):
        f_scores = [s.get("faithfulness") for s in scores if s.get("faithfulness") is not None]
    else:
        f_scores = [v for v in scores.get("faithfulness", []) if v is not None]
    f_mean = sum(f_scores) / len(f_scores) if f_scores else 0.0
    print(f"\nFaithfulness: {f_mean:.3f} (цель > 0.90)")

if __name__ == "__main__":
    main()
