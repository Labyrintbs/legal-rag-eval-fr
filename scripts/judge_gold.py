"""Blind second opinion of DeepSeek on gold lists, next to the assistant's audit.

For each selected question: the gold articles plus the top dense-search articles in the question's
language, in random order, graded by the judge without knowing the gold. Results go to
data/gold/judge_<tag>.json. Default is a dry run (worst-case cost); --run spends money; --report FILE
compares a saved run with the gold, no API call.
"""

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from itertools import repeat
from pathlib import Path

from legalrag import db, embed, goldjudge, llm
from legalrag import questiongen as qg
from legalrag.gold import GoldQuestion, load_gold
from legalrag.smoke import Question, embed_questions, nearest

MODEL = "deepseek-v4-pro"
MAX_TOKENS = 8000
POOL = 8
OUT = Path("data/gold")


def split_label(label: str) -> tuple[str, str, str]:
    if label.startswith("art "):
        return "rgpd", "article", label[4:]
    if label.startswith("rct "):
        return "rgpd", "recital", label[4:]
    return "code_travail", "article", label


def article_texts(conn, labels: set[str], lang: str) -> dict[str, tuple[str, str]]:
    texts = {}
    for label in labels:
        source, kind, num = split_label(label)
        row = conn.execute(
            "SELECT section_path, body_text FROM articles WHERE source_code = %s AND kind = %s"
            " AND article_num = %s AND lang = %s LIMIT 1", (source, kind, num, "fr" if source == "code_travail" else lang),
        ).fetchone()
        texts[label] = (qg.context_of(row[0]), row[1])
    return texts


def pooled_labels(conn, run_id: int, vectors, questions: list[GoldQuestion]) -> dict[str, list[str]]:
    """Gold labels plus the first POOL distinct articles of the dense search in the question's language."""
    pooled = {}
    for q, vector in zip(questions, vectors, strict=True):
        found = []
        for hit in nearest(conn, run_id, vector, 60):
            if hit.lang == q.lang and hit.label not in found:
                found.append(hit.label)
        pooled[q.id] = [g.article for g in q.gold] + found[:POOL]
    return pooled


def judge_one(http, budget, tag, messages):
    return qg.run_call(http, budget, f"{tag}-judge", MODEL, messages, MAX_TOKENS, thinking=True, reasoning_effort="low")


def select(questions: list[GoldQuestion]) -> list[GoldQuestion]:
    """needs_review lists, hand-written and sheet questions: the ones with no model-written check."""
    return [q for q in questions
            if q.review.status == "needs_review" or q.provenance.method in ("hand_written", "ministry_sheet")]


def report(path: Path, questions: list[GoldQuestion]) -> None:
    by_id = {q.id: q for q in questions}
    rows = json.loads(path.read_text())
    failed = [r["id"] for r in rows if r["compare"]["failed"]]
    shown = [r["compare"] for r in rows if not r["compare"]["failed"]]
    agree = [c for c in shown if not c["grade_differences"] and not c["missing_from_gold"] and c["kind_agrees"]]
    print(f"{len(rows)} questions judged, {len(failed)} failed {failed}, {len(agree)} fully agree with the gold")
    for c in shown:
        if c in agree:
            continue
        q = by_id[c["id"]]
        print(f"\n{c['id']} [{q.review.status}] {q.question[:90]}")
        if not c["kind_agrees"]:
            print(f"  kind: gold {c['kind'][0]}, judge {c['kind'][1]} (sure={c['sure']})")
        for article, (gold_grade, judge_grade) in c["grade_differences"].items():
            print(f"  {article}: gold {gold_grade}, judge {judge_grade}")
        if c["missing_from_gold"]:
            print(f"  judge also accepts, not in gold: {c['missing_from_gold']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", type=Path, default=OUT / "draft.jsonl")
    parser.add_argument("--tag", default="v1")
    parser.add_argument("--judge", default="judge.v1")
    parser.add_argument("--only", nargs="+", default=[], help="question id prefixes to judge, e.g. hw smoke")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--run-cap", type=float, default=1.0)
    parser.add_argument("--run", action="store_true", help="spend money; default is a dry run")
    parser.add_argument("--report", type=Path, help="compare a saved run with the gold, no API call")
    args = parser.parse_args()

    questions = load_gold(args.gold)
    if args.report:
        report(args.report, questions)
        return
    chosen = [q for q in select(questions) if not args.only or q.id.startswith(tuple(args.only))]
    prompts = qg.load_prompts(qg.PROMPTS / "gold_judge.yaml")
    with db.connect() as conn:
        run_id = conn.execute("SELECT id FROM chunking_runs WHERE name = 'default'").fetchone()[0]
        vectors = embed_questions(
            [Question(id=0, group=q.group, lang=q.lang, question=q.question) for q in chosen],
            embed.SentenceTransformerEmbedder("auto"),
        )
        pooled = pooled_labels(conn, run_id, vectors, chosen)
        jobs = []
        for q in chosen:
            texts = article_texts(conn, set(pooled[q.id]), q.lang)
            candidates = goldjudge.shuffled_candidates(pooled[q.id], texts, q.id)
            jobs.append((q, candidates, goldjudge.judge_messages(prompts, args.judge, q.question, candidates)))
    worst = sum(llm.worst_case_cost(MODEL, llm.estimate_tokens("".join(m["content"] for m in msgs)), MAX_TOKENS)
                for _, _, msgs in jobs)
    print(f"{len(jobs)} questions, {sum(len(c) for _, c, _ in jobs)} candidate articles; worst case {worst:.4f} USD; "
          f"run cap {args.run_cap}")
    if not args.run:
        return

    tag = f"gold-{args.tag}"
    budget = llm.Budget(run_cap=args.run_cap, total_cap=5.0)
    with llm.make_http(os.environ["DEEPSEEK_API_KEY"]) as http, ThreadPoolExecutor(args.workers) as pool:
        llm.record_balance(llm.LEDGER, llm.balance(http), f"before-{tag}")
        verdicts = list(pool.map(judge_one, repeat(http), repeat(budget), repeat(tag), [m for *_, m in jobs]))
        llm.record_balance(llm.LEDGER, llm.balance(http), f"after-{tag}")
    rows = []
    for (q, candidates, _), (verdict, error) in zip(jobs, verdicts, strict=True):
        verdict = verdict or {"error": error}
        rows.append({"id": q.id, "candidates": {c.id: c.label for c in candidates}, "verdict": verdict,
                     "compare": goldjudge.compare(q, verdict, candidates)})
    out = OUT / f"judge_{args.tag}.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    print(f"written {out}; spent {budget.spent:.4f} USD estimated")
    report(out, questions)


if __name__ == "__main__":
    main()
