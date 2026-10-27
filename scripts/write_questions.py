"""Write and review the questions of one drawn batch (data/drawn/NAME.json).

Flash writes one question per article and style; pro reviews every question with thinking on; the
automatic checks run on all. Calls run in parallel under one shared Budget. Default is a dry run
(worst-case cost, no call); --run spends money.
"""

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from itertools import repeat
from pathlib import Path

from legalrag import llm
from legalrag import questiongen as qg

FAMILIES = ["plain", "lay"]
WRITER, REVIEWER = "deepseek-flash", "deepseek-v4-pro"
WRITER_MAX_TOKENS = 400
# Thinking tokens count against max_tokens: a review at effort low used 2,500 on average, 4,000 failed.
REVIEWER_MAX_TOKENS = {"low": 8000, "high": 12000, "max": 12000}
OUT = Path("data/questions")


def write_one(http, budget, tag, job):
    _, _, messages = job
    return qg.run_call(http, budget, f"{tag}-writer", WRITER, messages, WRITER_MAX_TOKENS)


def review_one(http, budget, tag, prompts, reviewer, effort, item):
    article, style, question = item
    messages = qg.reviewer_messages(
        prompts, reviewer, style, article["body"], qg.context_of(article["section_path"]), question
    )
    return qg.run_call(
        http, budget, f"{tag}-reviewer", REVIEWER, messages, REVIEWER_MAX_TOKENS[effort],
        thinking=True, reasoning_effort=effort,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name", help="drawn batch, e.g. batch2")
    parser.add_argument("--version", default="v3", help="writer style version")
    parser.add_argument("--reviewer", default="reviewer.v4", help="reviewer prompt id")
    parser.add_argument("--effort", default="low", choices=list(REVIEWER_MAX_TOKENS), help="reviewer thinking effort")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--run-cap", type=float, default=1.0, help="USD this run may spend")
    parser.add_argument("--run", action="store_true", help="spend money; default is a dry run")
    args = parser.parse_args()
    tag = f"{args.name}-{args.version}"

    articles = json.loads((Path("data/drawn") / f"{args.name}.json").read_text())["articles"]
    writer_prompts = qg.load_prompts(qg.PROMPTS / "question_writer.yaml")
    reviewer_prompts = qg.load_prompts(qg.PROMPTS / "question_reviewer.yaml")
    checks = reviewer_prompts["reviewers"][args.reviewer]["checks"]

    jobs = [
        (a, f"{family}.{args.version}",
         qg.writer_messages(writer_prompts, f"{family}.{args.version}", a["body"], qg.context_of(a["section_path"])))
        for a in articles for family in FAMILIES
    ]
    writer_cost = sum(
        llm.worst_case_cost(WRITER, llm.estimate_tokens("".join(m["content"] for m in messages)), WRITER_MAX_TOKENS)
        for _, _, messages in jobs
    )
    review_cost = sum(
        llm.worst_case_cost(REVIEWER, llm.estimate_tokens(a["body"]) + 1000, REVIEWER_MAX_TOKENS[args.effort])
        for a, _, _ in jobs
    )
    print(f"{len(jobs)} writer calls + {len(jobs)} reviews (thinking {args.effort}); worst case if every "
          f"call used its full max_tokens: {writer_cost + review_cost:.4f} USD; run cap {args.run_cap}")
    if not args.run:
        return

    budget = llm.Budget(run_cap=args.run_cap, total_cap=5.0)
    with llm.make_http(os.environ["DEEPSEEK_API_KEY"]) as http, ThreadPoolExecutor(args.workers) as pool:
        llm.record_balance(llm.LEDGER, llm.balance(http), f"before-{tag}")
        written = list(pool.map(write_one, repeat(http), repeat(budget), repeat(tag), jobs))
        to_review = [(a, s, q) for (a, s, _), (q, _) in zip(jobs, written, strict=True) if q and q.get("question")]
        reviewed = iter(list(pool.map(
            review_one, repeat(http), repeat(budget), repeat(tag), repeat(reviewer_prompts),
            repeat(args.reviewer), repeat(args.effort), to_review,
        )))
        llm.record_balance(llm.LEDGER, llm.balance(http), f"after-{tag}")

    records = []
    for (article, style, _), (question, error) in zip(jobs, written, strict=True):
        earlier = [r["question"]["question"] for r in records
                   if r["article"] == article["article"] and r["source"] == article["source"] and r["question"]]
        max_overlap = writer_prompts["styles"][style]["max_overlap"]
        flags = qg.automatic_checks(question, article["body"], max_overlap, earlier) if question else [error]
        result = None
        if question and question.get("question"):
            result, review_error = next(reviewed)
            result = result or {"error": review_error}
        problems = qg.review_problems(result, checks)
        records.append({
            "source": article["source"], "article": article["article"], "pool": article["pool"],
            "style": style, "writer": WRITER, "reviewer": REVIEWER,
            "prompt_hash": qg.prompt_hash(writer_prompts, style), "reviewer_id": args.reviewer,
            "reviewer_effort": args.effort, "question": question, "flags": flags,
            "overlap": qg.overlap(question["question"], article["body"]) if question and question.get("question") else None,
            "review": result, "review_problems": problems,
            "status": "doubtful" if flags or problems else "accepted",
        })

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{tag}.json").write_text(json.dumps(records, ensure_ascii=False, indent=1))
    accepted = sum(r["status"] == "accepted" for r in records)
    print(f"written data/questions/{tag}.json: {accepted} accepted, {len(records) - accepted} doubtful; "
          f"spent {budget.spent:.4f} USD estimated")


if __name__ == "__main__":
    main()
