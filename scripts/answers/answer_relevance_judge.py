"""Answer relevancy of the answers of a pilot run (step 0f): the judge `answer_relevance.v1` on every answered question,
and on wrong pairs as a control (each answerable answer with a random question and with the nearest question about
other articles; needs the dev question vectors of the CI fixture, so dev only). Writes the verdicts
`data/judge/answer-relevance-<tag>.jsonl`, a summary, and a blind label sheet `data/labels/answer-relevance-<tag>.html`:
every answer the judge does not call "addresses", 10 that it does, and a few wrong pairs, shuffled under neutral names.
Spends a few cents of DeepSeek money.
  uv run --env-file .env python scripts/answers/answer_relevance_judge.py --tag flash-v3
"""

import argparse
import json
import os
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from legalrag import llm
from legalrag.evaluation import answer_relevance as ar
from legalrag.evaluation import cifixture, gold, judgecall, labelsheet
from legalrag.evaluation.questiongen import load_prompts

FIXTURE = Path("data/ci/fixture")
PILOT = Path("data/pilot")
JUDGE = Path("data/judge")
LABELS = Path("data/labels")


def kind_counts(rows: list[dict]) -> dict:
    """Judge labels by kind of pair (matched, random, near) and, for the matched ones, by kind of question."""
    out = {}
    for pair_kind in ar.KINDS:
        picked = [r["label"] for r in rows if r["pair_kind"] == pair_kind and "label" in r]
        out[pair_kind] = {"n": len(picked), **{label: picked.count(label) for label in ar.LABELS}}
    for question_kind in sorted({r["question_kind"] for r in rows}):
        picked = [r["label"] for r in rows if r["pair_kind"] == "matched" and r["question_kind"] == question_kind and "label" in r]
        out[f"matched, {question_kind}"] = {"n": len(picked), **{label: picked.count(label) for label in ar.LABELS}}
    return out


def sheet_items(rows: list[dict], pairs: dict[str, ar.Pair], seed: int, n_addresses: int = 10, n_controls: int = 4) -> tuple[list, dict]:
    """The pairs to label by hand, shuffled and under neutral names, and the map from names to keys."""
    rng = random.Random(seed)
    judged = [r for r in rows if "label" in r]
    flagged = [r for r in judged if r["pair_kind"] == "matched" and r["label"] != "addresses"]
    fine = [r for r in judged if r["pair_kind"] == "matched" and r["label"] == "addresses"]
    wrong = [r for r in judged if r["pair_kind"] != "matched"]
    chosen = flagged + rng.sample(fine, min(n_addresses, len(fine))) + rng.sample(wrong, min(n_controls, len(wrong)))
    rng.shuffle(chosen)
    names = {f"item-{i:02d}": r["key"] for i, r in enumerate(chosen, 1)}
    return [(name, pairs[key].question, pairs[key].answer) for name, key in names.items()], names


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tag", default="flash-v3", help="the pilot file data/pilot/answers_<tag>.jsonl")
    parser.add_argument("--no-controls", action="store_true", help="only the real pairs (needed for a test-half tag)")
    parser.add_argument("--seed", type=int, default=20261118)
    parser.add_argument("--run-cap", type=float, default=0.3, help="most USD this run may spend")
    args = parser.parse_args()

    every = {q.id: q for q in gold.load_gold(Path("eval/gold.jsonl"))}
    rows = [r for r in labelsheet.read_rows(PILOT / f"answers_{args.tag}.jsonl") if r["outcome"] == "answered"]
    answers = {r["id"]: "\n".join(c.text for c in labelsheet.parse_answer(r["text"])) for r in rows}
    pairs = {f"{r['id']}|matched": ar.Pair(f"{r['id']}|matched", every[r["id"]].question, answers[r["id"]], "matched") for r in rows}
    if not args.no_controls:
        fixture = cifixture.read(FIXTURE)
        vectors = dict(zip(fixture.questions, fixture.question_vectors, strict=True))
        questions = {i: q.question for i, q in every.items() if i in vectors and q.gold}
        gold_sets = {i: {g.article for g in every[i].gold} for i in questions}
        rng = random.Random(args.seed)
        for r in rows:
            if r["id"] in questions:
                pairs.update({p.key: p for p in ar.wrong_pairs(r["id"], {r["id"]: answers[r["id"]]}, questions, vectors, gold_sets, rng)})
    prompt = load_prompts(Path("prompts/answer_relevance.yaml"))["prompts"]["answer_relevance.v1"]
    budget = llm.Budget(run_cap=args.run_cap, total_cap=5.0)
    with llm.make_http(os.environ["DEEPSEEK_API_KEY"]) as http, ThreadPoolExecutor(6) as pool:
        jobs = {key: pool.submit(judgecall.ask, http, budget, f"answer-relevance-{args.tag}", ar.MODEL,
                                 judgecall.chat_messages(prompt, question=p.question, answer=p.answer), prompt["max_tokens"], ar.Verdict)
                for key, p in pairs.items()}
        results = {key: job.result() for key, job in jobs.items()}
    out = [{"key": key, "pair_kind": pairs[key].kind, "question_kind": every[key.split("|")[0]].kind,
            **({"label": r["value"].label, "reason": r["value"].reason} if "value" in r else {"error": r["error"]})}
           for key, r in results.items()]
    JUDGE.mkdir(parents=True, exist_ok=True)
    (JUDGE / f"answer-relevance-{args.tag}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out))
    summary = {"pairs": len(out), "errors": sum("error" in r for r in out), "labels": kind_counts(out)}
    ordinal = {k: [ar.ORDER[r["label"]] for r in out if r["pair_kind"] == k and "label" in r] for k in ar.KINDS}
    for wrong in ("random", "near"):
        if ordinal[wrong]:
            summary[f"separation_vs_{wrong}"] = ar.separation(ordinal["matched"], ordinal[wrong])
    print(json.dumps(summary, indent=1))
    items, names = sheet_items(out, pairs, args.seed)
    LABELS.mkdir(parents=True, exist_ok=True)
    (LABELS / f"answer-relevance-{args.tag}.html").write_text(labelsheet.render_answer_relevance(items, f"answer-relevance-{args.tag}"))
    (LABELS / f"answer-relevance-{args.tag}.names.json").write_text(json.dumps(names, indent=1))
    print(f"{len(items)} items on the sheet {LABELS / f'answer-relevance-{args.tag}.html'}")


if __name__ == "__main__":
    main()
