"""Test reviewers against the questions the assistant audited by hand (v2 and v3 batches).

--run MODEL REVIEWER reviews every stored question again (temperature 0) and saves the pipeline
outcome (automatic checks with the current thresholds, plus the reviewer's checks). --union A B ...
combines saved runs, flagging a question if any of them does, and compares with the audit.
Default is a dry run; --run spends money.
"""

import argparse
import json
import os
from pathlib import Path

from legalrag import llm
from legalrag import questiongen as qg

# Thinking tokens count against max_tokens (one test used 2,245 of 2,508 at effort low).
MAX_TOKENS = {"off": 800, "low": 4000, "high": 8000, "max": 8000}
QUESTIONS = Path("data/questions")
# Questions the audit rejects or rewrites: (file, article, style). The audit files give the reasons.
REJECTED = {
    ("batch1b", "L6325-10", "plain.v2"), ("batch1b", "L6325-10", "lay.v2"),
    ("batch1b", "R4227-55", "plain.v2"), ("batch1b", "R4227-55", "lay.v2"),
    ("batch1b", "R7422-11", "lay.v2"), ("batch1b", "L2232-25", "lay.v2"), ("batch1b", "L2315-38", "lay.v2"),
    ("batch1b-v3", "L1225-56", "plain.v3"), ("batch1b-v3", "L2315-38", "lay.v3"),
    ("batch1b-v3", "L2232-25", "lay.v3"), ("batch1b-v3", "15", "lay.v3"),
    ("batch1b-v3", "R7422-11", "lay.v3"), ("batch1b-v3", "82", "lay.v3"),
    # Added after the thinking-on reviewer showed the first audit was too lenient (2026-10-27).
    ("batch1b", "L1225-56", "lay.v2"),  # the question gives the answer ("sans que ça me soit payé")
    ("batch1b", "R7422-11", "plain.v2"),  # never names the travailleurs à domicile
    ("batch1b-v3", "L1233-24-1", "lay.v3"),  # a technical term in a lay question
}
# Fair but strict points (answer omits an alternative, scope detail): kept out of both counts.
BORDERLINE = {
    ("batch1b", "L1233-24-1", "plain.v2"), ("batch1b", "L1233-24-1", "lay.v2"),
    ("batch1b", "L2315-38", "plain.v2"), ("batch1b-v3", "L2315-38", "plain.v3"),
    ("batch1b-v3", "82", "plain.v3"),
}


def audit_label(file: str, article: str, style: str) -> str:
    key = (file, article, style)
    return "reject" if key in REJECTED else "borderline" if key in BORDERLINE else "accept"


def result_path(model: str, reviewer: str, mode: str = "off") -> Path:
    suffix = "" if mode == "off" else f"_think-{mode}"
    return QUESTIONS / f"reviewer_eval_{model}_{reviewer}{suffix}.json"


def review_all(args) -> None:
    articles = {a["article"]: a for a in json.loads(Path("data/drawn/batch1b.json").read_text())["articles"]}
    reviewer_prompts = qg.load_prompts(qg.PROMPTS / "question_reviewer.yaml")
    writer = qg.load_prompts(qg.PROMPTS / "question_writer.yaml")
    jobs = []
    for file in ("batch1b", "batch1b-v3"):
        for record in json.loads((QUESTIONS / f"{file}.json").read_text()):
            if record["question"]:
                article = articles[record["article"]]
                messages = qg.reviewer_messages(
                    reviewer_prompts, args.reviewer, record["style"], article["body"],
                    qg.context_of(article["section_path"]), record["question"],
                )
                jobs.append((file, record, article, messages))
    worst = sum(
        llm.worst_case_cost(
            args.model, llm.estimate_tokens("".join(m["content"] for m in messages)), MAX_TOKENS[args.thinking]
        )
        for *_, messages in jobs
    )
    print(f"{len(jobs)} reviews with {args.model} {args.reviewer} thinking={args.thinking}; "
          f"worst case {worst:.4f} USD")
    if not args.run:
        return

    budget = llm.Budget(run_cap=1.0, total_cap=5.0)
    checks = reviewer_prompts["reviewers"][args.reviewer]["checks"]
    results = []
    with llm.make_http(os.environ["DEEPSEEK_API_KEY"]) as http:
        label = f"reviewer-eval-{args.model}-{args.reviewer}-think-{args.thinking}"
        llm.record_balance(llm.LEDGER, llm.balance(http), f"before-{label}")
        thinking = args.thinking != "off"
        for file, record, article, messages in jobs:
            review, error = qg.run_call(
                http, budget, label, args.model, messages, MAX_TOKENS[args.thinking], thinking=thinking,
                reasoning_effort=args.thinking if thinking else None,
                temperature=None if thinking else 0.0,  # no effect in thinking mode
            )
            review = review or {"error": error}
            # The same writer family (plain or lay) with today's thresholds.
            max_overlap = writer["styles"][f"{record['style'].split('.')[0]}.v3"]["max_overlap"]
            results.append({
                "file": file, "article": record["article"], "style": record["style"],
                "audit": audit_label(file, record["article"], record["style"]),
                "flags": qg.automatic_checks(record["question"], article["body"], max_overlap, []),
                "review_problems": qg.review_problems(review, checks), "review": review,
                "question": record["question"]["question"],
            })
        llm.record_balance(llm.LEDGER, llm.balance(http), f"after-{label}")
    result_path(args.model, args.reviewer, args.thinking).write_text(
        json.dumps(results, ensure_ascii=False, indent=1)
    )
    print(f"spent {budget.spent:.4f} USD estimated")


def union(paths: list[Path]) -> None:
    """Flag a question if any run flags it; the automatic flags are the same in every run."""
    runs = [json.loads(p.read_text()) for p in paths]
    merged = []
    for rows in zip(*runs, strict=True):
        problems = sorted({p for r in rows for p in r["review_problems"]})
        merged.append({**rows[0], "review_problems": problems})
    # The labels are recomputed, so older result files get the corrected audit.
    for r in merged:
        r["audit"] = audit_label(r["file"], r["article"], r["style"])
    bad = [r for r in merged if r["audit"] == "reject"]
    good = [r for r in merged if r["audit"] == "accept"]
    caught = [r for r in bad if r["flags"] or r["review_problems"]]
    alarms = [r for r in good if r["flags"] or r["review_problems"]]
    print(f"{' + '.join(p.stem.removeprefix('reviewer_eval_') for p in paths)}")
    print(f"  caught {len(caught)} of {len(bad)} audit rejects; "
          f"fine questions flagged {len(alarms)} of {len(good)}")
    for r in bad:
        if r not in caught:
            print(f"  MISSED {r['file']} {r['article']} {r['style']}")
    for r in alarms:
        print(f"  ALARM  {r['file']} {r['article']} {r['style']}: {r['flags'] + r['review_problems']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="deepseek-v4-pro")
    parser.add_argument("--reviewer", default="reviewer.v3")
    parser.add_argument("--thinking", choices=list(MAX_TOKENS), default="off",
                        help="off, or the reasoning effort when thinking is on")
    parser.add_argument("--run", action="store_true", help="spend money; default is a dry run")
    parser.add_argument("--union", nargs="+", metavar="MODEL:REVIEWER[:MODE]",
                        help="combine saved runs, no API call")
    args = parser.parse_args()
    if args.union:
        union([result_path(*spec.split(":")) for spec in args.union])
    else:
        review_all(args)


if __name__ == "__main__":
    main()
