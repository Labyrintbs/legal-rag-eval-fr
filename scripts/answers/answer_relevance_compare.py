"""Compares two ways to measure answer relevancy (does the answer respond to the question?) on a small subset of dev
answers (step 0f): the judge with three labels (`answer_relevance.v1`) and the Ragas style (`ragas.v1` plus bge-m3
cosines). Each answer is also given with a wrong question (random, and the nearest question about other articles); a
good measure scores those lower. Spends a few cents of DeepSeek money. Output: data/judge/answer-relevance-compare.json.
  uv run --env-file .env --extra embed python scripts/answers/answer_relevance_compare.py --n 10
"""

import argparse
import json
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from legalrag import llm
from legalrag.evaluation import answer_relevance as ar
from legalrag.evaluation import cifixture, gold, judgecall, labelsheet
from legalrag.evaluation.questiongen import load_prompts
from legalrag.index import embed

FIXTURE = Path("data/ci/fixture")  # holds the vectors of the dev questions
PILOT = Path("data/pilot/answers_flash-v3.jsonl")
OUT = Path("data/judge/answer-relevance-compare.json")


def table(pairs: list[ar.Pair], judged: list[dict], scores: list[float | None]) -> dict:
    result = {}
    for kind in ar.KINDS:
        picked = [i for i, p in enumerate(pairs) if p.kind == kind]
        labels = Counter(judged[i]["value"].label for i in picked if "value" in judged[i])
        values = [scores[i] for i in picked if scores[i] is not None]
        result[kind] = {"n": len(picked), "judge_labels": {label: labels.get(label, 0) for label in ar.LABELS},
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
    pairs = ar.make_pairs(answers, questions, vectors, gold_sets, args.n, args.seed)

    prompts = load_prompts(Path("prompts/answer_relevance.yaml"))["prompts"]
    judge_prompt, ragas_prompt = prompts["answer_relevance.v1"], prompts["ragas.v1"]
    budget = llm.Budget(run_cap=args.run_cap, total_cap=5.0)
    with llm.make_http(os.environ["DEEPSEEK_API_KEY"]) as http, ThreadPoolExecutor(6) as pool:
        judge_jobs = [pool.submit(judgecall.ask, http, budget, "answer-relevance-judge", ar.MODEL,
                                  judgecall.chat_messages(judge_prompt, question=p.question, answer=p.answer),
                                  judge_prompt["max_tokens"], ar.Verdict) for p in pairs]
        ragas_jobs = [pool.submit(judgecall.ask, http, budget, "answer-relevance-ragas", ar.MODEL,
                                  judgecall.chat_messages(ragas_prompt, answer=p.answer), ragas_prompt["max_tokens"], ar.Generated)
                      for p in pairs]
        judged, generated = [j.result() for j in judge_jobs], [j.result() for j in ragas_jobs]

    embedder = embed.SentenceTransformerEmbedder("cpu")
    scores: list[float | None] = []
    for p, g in zip(pairs, generated, strict=True):
        if "error" in g:
            scores.append(None)
            continue
        asked = embed.embed_queries([p.question], embedder)[0]
        scores.append(ar.ragas_score(asked, embed.embed_queries(g["value"].questions, embedder)))

    result = table(pairs, judged, scores)
    ordinal = [ar.ORDER[j["value"].label] if "value" in j else None for j in judged]
    for wrong in ("random", "near"):
        for name, values in (("judge", ordinal), ("ragas", scores)):
            by = {kind: [v for p, v in zip(pairs, values, strict=True) if p.kind == kind and v is not None] for kind in ("matched", wrong)}
            result[f"separation_{name}_vs_{wrong}"] = ar.separation(by["matched"], by[wrong])
    detail = [{"key": p.key, "question": p.question, "answer": p.answer, "judge": (j["value"].label, j["value"].reason) if "value" in j else j,
               "generated": g["value"].questions if "value" in g else g, "ragas": s}
              for p, j, g, s in zip(pairs, judged, generated, scores, strict=True)]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"summary": result, "pairs": detail}, ensure_ascii=False, indent=1))
    print(json.dumps(result, indent=1))
    print(f"details in {OUT}")


if __name__ == "__main__":
    main()
