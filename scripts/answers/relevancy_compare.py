"""Compares two ways to measure whether an answer addresses its question, on a small subset of dev answers (step 0f):
the judge with three labels (`relevance.v1`) and the Ragas style (`ragas.v1` plus bge-m3 cosines). Each answer is
also given with a wrong question (random, and the nearest question about other articles); a good measure scores those
lower. Spends a few cents of DeepSeek money. Output: data/judge/relevance-compare.json and a table on screen.
  uv run --extra embed python scripts/answers/relevancy_compare.py --n 10
"""

import argparse
import json
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from pydantic import BaseModel, ValidationError

from legalrag import llm
from legalrag.evaluation import cifixture, gold, labelsheet, relevance
from legalrag.evaluation.questiongen import load_prompts
from legalrag.index import embed

MODEL = "deepseek-flash"
FIXTURE = Path("data/ci/fixture")  # holds the vectors of the dev questions
PILOT = Path("data/pilot/answers_flash-v3.jsonl")
OUT = Path("data/judge/relevance-compare.json")


def ask(http, budget, label: str, messages: list[dict], max_tokens: int, shape: type[BaseModel]) -> dict:
    """One call, no retry: {"value": parsed reply} or {"error": ...}."""
    try:
        text = llm.chat(http, llm.LEDGER, budget, label, MODEL, messages, max_tokens, json_mode=True, temperature=0)
        return {"value": shape.model_validate_json(text)}
    except (ValidationError, ValueError, KeyError, llm.BudgetExceeded) as error:
        return {"error": f"{type(error).__name__}: {error}"}


def chat_messages(prompt: dict, **fields: str) -> list[dict]:
    return [{"role": "system", "content": prompt["system"].strip()}, {"role": "user", "content": prompt["user"].format(**fields)}]


def table(pairs: list[relevance.Pair], judged: list[dict], scores: list[float | None]) -> dict:
    result = {}
    for kind in relevance.KINDS:
        picked = [i for i, p in enumerate(pairs) if p.kind == kind]
        labels = Counter(judged[i]["value"].label for i in picked if "value" in judged[i])
        values = [scores[i] for i in picked if scores[i] is not None]
        result[kind] = {"n": len(picked), "judge_labels": {label: labels.get(label, 0) for label in relevance.LABELS},
                        "judge_errors": sum("error" in judged[i] for i in picked),
                        "ragas_mean": float(np.mean(values)) if values else None,
                        "ragas_min": min(values) if values else None, "ragas_max": max(values) if values else None}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n", type=int, default=10, help="answers drawn; each gives three pairs")
    parser.add_argument("--seed", type=int, default=20261117)
    parser.add_argument("--run-cap", type=float, default=0.2, help="most USD this run may spend")
    args = parser.parse_args()

    fixture = cifixture.read(FIXTURE)
    vectors = dict(zip(fixture.questions, fixture.question_vectors, strict=True))
    questions = {q.id: q.question for q in gold.load_gold(Path("eval/gold.jsonl")) if q.id in vectors and q.gold}
    gold_sets = {q.id: {g.article for g in q.gold} for q in gold.load_gold(Path("eval/gold.jsonl")) if q.id in questions}
    rows = [r for r in labelsheet.read_rows(PILOT) if r["kind"] == "answerable" and r["outcome"] == "answered"]
    answers = {r["id"]: "\n".join(c.text for c in labelsheet.parse_answer(r["text"])) for r in rows}
    pairs = relevance.make_pairs(answers, questions, vectors, gold_sets, args.n, args.seed)

    prompts = load_prompts(Path("prompts/relevance.yaml"))["prompts"]
    judge_prompt, ragas_prompt = prompts["relevance.v1"], prompts["ragas.v1"]
    budget = llm.Budget(run_cap=args.run_cap, total_cap=5.0)
    with llm.make_http(os.environ["DEEPSEEK_API_KEY"]) as http, ThreadPoolExecutor(6) as pool:
        judge_jobs = [pool.submit(ask, http, budget, "relevance-judge", chat_messages(judge_prompt, question=p.question, answer=p.answer),
                                  judge_prompt["max_tokens"], relevance.Verdict) for p in pairs]
        ragas_jobs = [pool.submit(ask, http, budget, "relevance-ragas", chat_messages(ragas_prompt, answer=p.answer),
                                  ragas_prompt["max_tokens"], relevance.Generated) for p in pairs]
        judged, generated = [j.result() for j in judge_jobs], [j.result() for j in ragas_jobs]

    embedder = embed.SentenceTransformerEmbedder("cpu")
    scores: list[float | None] = []
    for p, g in zip(pairs, generated, strict=True):
        if "error" in g:
            scores.append(None)
            continue
        asked = embed.embed_queries([p.question], embedder)[0]
        scores.append(relevance.ragas_score(asked, embed.embed_queries(g["value"].questions, embedder)))

    result = table(pairs, judged, scores)
    ordinal = [relevance.ORDER[j["value"].label] if "value" in j else None for j in judged]
    for wrong in ("random", "near"):
        for name, values in (("judge", ordinal), ("ragas", scores)):
            by = {kind: [v for p, v in zip(pairs, values, strict=True) if p.kind == kind and v is not None] for kind in ("matched", wrong)}
            result[f"separation_{name}_vs_{wrong}"] = relevance.separation(by["matched"], by[wrong])
    result["cost_note"] = "see `make llm-ledger`: labels relevance-judge and relevance-ragas"
    detail = [{"key": p.key, "question": p.question, "answer": p.answer, "judge": (j["value"].label, j["value"].reason) if "value" in j else j,
               "generated": g["value"].questions if "value" in g else g, "ragas": s}
              for p, j, g, s in zip(pairs, judged, generated, scores, strict=True)]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"summary": result, "pairs": detail}, ensure_ascii=False, indent=1))
    print(json.dumps(result, indent=1))
    print(f"details in {OUT}")


if __name__ == "__main__":
    main()
