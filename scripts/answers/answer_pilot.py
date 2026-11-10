"""Pilot of the answer path on the dev half (step 0d): retrieval, numbered context, one model, the citation checks.
Nothing is written to the traces table. Output: data/pilot/answers_<tag>.jsonl and a summary on screen.
Measures what needs no judge: format, citations that exist, whether the cited articles are the gold ones,
refusals by question kind, tokens, cost and time. It does not say whether an answer is true.
"""

import argparse
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

from llama_index.llms.deepseek import DeepSeek

from legalrag.answering import rag, search
from legalrag.evaluation import gold
from legalrag.evaluation.questiongen import load_prompts as qg_load_prompts
from legalrag.index import db, embed

RUN = "default"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True, help="deepseek-flash or deepseek-v4-pro")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--n", type=int, default=None, help="trial: only the first N dev questions")
    parser.add_argument("--threshold", type=float, default=search.WEAK_THRESHOLD, help="0 switches the pre-filter off")
    parser.add_argument("--prompt", default="answer.v1")
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()

    prompt = qg_load_prompts(Path("prompts/answer.yaml"))["prompts"][args.prompt]
    questions = [q for q in gold.load_gold(Path("eval/gold.jsonl")) if q.split == "dev" and q.lang == "fr"][: args.n]
    llm = DeepSeek(model=args.model, api_key=os.environ["DEEPSEEK_API_KEY"], temperature=0,
                   additional_kwargs={"extra_body": {"thinking": {"type": "disabled"}}}, max_tokens=prompt["max_tokens"])
    with db.connect() as conn:
        run_id = conn.execute("SELECT id FROM chunking_runs WHERE name = %s", (RUN,)).fetchone()[0]
    engine = rag.AnswerEngine(
        retriever=rag.LegalRetriever(db.connect, run_id, embed.SentenceTransformerEmbedder(args.device), "fr"),
        postprocessor=rag.NumberUnits(), llm=llm, prompt=prompt, model=args.model, prompt_id=args.prompt,
        threshold=args.threshold, ledger_label=f"answer-pilot-{args.tag}")

    rows = []
    for q in questions:
        result = engine.query(q.question).metadata["result"]
        cited = sorted({c.label for _, cs in (result.resolved.claims if result.resolved else []) for c in cs})
        rows.append({"id": q.id, "kind": q.kind, "outcome": result.outcome, "text": result.text, "cited": cited,
                     "gold": [g.article for g in q.gold], "primary": [g.article for g in q.gold if g.grade == 2],
                     "top5": [h.label for h in result.hits], "top_similarity": result.hits[0].similarity if result.hits else None,
                     "tokens_in": result.tokens_in, "tokens_out": result.tokens_out, "cost_usd": result.cost_usd,
                     "llm_ms": result.llm_ms, "total_ms": result.total_ms, "error": result.error, "reason": result.reason,
                     "dropped": ([len(result.resolved.dropped_ids), result.resolved.dropped_claims] if result.resolved else None),
                     "raw": result.raw})
    out = Path("data/pilot") / f"answers_{args.tag}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    summarize(rows, args)
    print(f"written {out}")


def summarize(rows: list[dict], args) -> None:
    by_kind = defaultdict(Counter)
    for r in rows:
        by_kind[r["kind"]][r["outcome"]] += 1
    print(f"model {args.model}, prompt {args.prompt}, threshold {args.threshold}, {len(rows)} questions")
    for kind, counts in sorted(by_kind.items()):
        print(f"  {kind:<15} {dict(counts)}")
    answerable = [r for r in rows if r["kind"] == "answerable"]
    answered = [r for r in answerable if r["outcome"] == "answered"]
    gold_hit = [r for r in answered if set(r["cited"]) & set(r["gold"])]
    primary = [r for r in answered if set(r["cited"]) & set(r["primary"])]
    cited = [(a, r) for r in answered for a in r["cited"]]
    precise = sum(a in r["gold"] for a, r in cited)
    print(f"answerable: {len(answered)}/{len(answerable)} answered; cites a gold article in {len(gold_hit)}, a primary one in {len(primary)}; "
          f"{precise}/{len(cited)} cited articles are gold")
    others = [r for r in rows if r["kind"] != "answerable"]
    print(f"other kinds: {sum(r['outcome'] != 'answered' for r in others)}/{len(others)} refused")
    done = [r for r in rows if r["tokens_in"]]
    if done:
        print(f"{len(done)} model calls: {sum(r['tokens_in'] for r in done) / len(done):.0f} tokens in and "
              f"{sum(r['tokens_out'] for r in done) / len(done):.0f} out on average, {sum(r['cost_usd'] or 0 for r in done):.4f} USD in total, "
              f"model time median {sorted(r['llm_ms'] for r in done)[len(done) // 2]} ms")
    print(f"dropped ids or claims in {sum(1 for r in rows if r['dropped'] and any(r['dropped']))} answers")


if __name__ == "__main__":
    main()
