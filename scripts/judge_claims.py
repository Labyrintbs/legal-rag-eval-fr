"""Validate the claim judge against the labels made by hand (step 0d).

  --export FILE        the labelled claims without their labels (for a judge that runs outside this project)
  --run MODEL --tag T  the judge `judge.v1` on every labelled claim: data/judge/<T>.jsonl, then the score
  --score FILE         score a verdicts file (JSON lines: key, label, reason) against the labels
Spends model money only with --run, within a cap of --run-cap USD.
"""

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from legalrag import claimjudge, gold, labelsheet, llm
from legalrag import questiongen as qg

PILOT = Path("data/pilot/answers_flash-v3.jsonl")
OUT = Path("data/judge")
PENDING = ("mw-035|claim0",)  # not yet settled with the labeller: left out of the scores


def load_items(labels_path: Path, exclude: tuple[str, ...]) -> list[claimjudge.Item]:
    questions = {q.id: q.question for q in gold.load_gold(Path("eval/gold.jsonl"))}
    rows = [{**r, "question": questions[r["id"]]} for r in labelsheet.read_rows(PILOT)]
    checks = labelsheet.load_checks(Path("eval/answer_checks.json"), rows)
    labels = json.loads(labels_path.read_text())["labels"]
    return [i for i in claimjudge.collect(labels, rows, checks) if i.key not in exclude]


def judge_all(items: list[claimjudge.Item], model: str, think: bool, run_cap: float, workers: int, tag: str) -> list[dict]:
    prompt = qg.load_prompts(Path("prompts/judge.yaml"))["prompts"]["judge.v1"]
    budget = llm.Budget(run_cap=run_cap, total_cap=5.0)
    http = llm.make_http(os.environ["DEEPSEEK_API_KEY"])
    max_tokens = prompt["max_tokens_thinking"] if think else prompt["max_tokens"]

    def one(item: claimjudge.Item) -> dict:
        row = {"key": item.key, "human": item.human}
        try:
            text = llm.chat(http, llm.LEDGER, budget, f"judge-{tag}", model, claimjudge.messages(prompt, item), max_tokens,
                            thinking=think, json_mode=True, temperature=None if think else 0)
            row["label"], row["reason"] = claimjudge.parse(text)
        except (httpx.HTTPError, ValueError, KeyError, llm.BudgetExceeded) as error:
            row["error"] = f"{type(error).__name__}: {error}"
        return row

    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(one, items))


def score(items: list[claimjudge.Item], verdicts: list[dict]) -> None:
    by_key = {v["key"]: v for v in verdicts if v.get("label") in claimjudge.LABELS}
    scored = [(i, by_key[i.key]) for i in items if i.key in by_key]
    r = claimjudge.report([(i.human, v["label"]) for i, v in scored])
    print(f"{r['n']} of {len(items)} claims judged; agreement {r['agreement']:.0%}, kappa {r['kappa']:.2f}")
    print(f"errors (human: partly or not supported) caught: {r['errors_caught']} of {r['errors']}; "
          f"good claims flagged: {r['good_flagged']} of {r['good']}")
    print("human \\ judge", *claimjudge.LABELS, sep="\t")
    for human, row in r["confusion"].items():
        print(human, *(row[label] for label in claimjudge.LABELS), sep="\t")
    for item, verdict in scored:
        if item.human != verdict["label"]:
            print(f"\n{item.key}: human {item.human}, judge {verdict['label']}\n  claim: {item.claim}\n"
                  f"  reason: {verdict.get('reason', '')}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--labels", type=Path, default=Path("data/labels/answers.labels.json"))
    parser.add_argument("--exclude", nargs="*", default=list(PENDING))
    parser.add_argument("--export", type=Path)
    parser.add_argument("--run", metavar="MODEL")
    parser.add_argument("--think", action="store_true", help="thinking mode of the judge model")
    parser.add_argument("--tag")
    parser.add_argument("--score", type=Path)
    parser.add_argument("--run-cap", type=float, default=0.5)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    items = load_items(args.labels, tuple(args.exclude))
    if args.export:
        args.export.parent.mkdir(parents=True, exist_ok=True)
        args.export.write_text("".join(json.dumps({"key": i.key, "claim": i.claim, "passages": i.passages}, ensure_ascii=False)
                                       + "\n" for i in items))
        print(f"{len(items)} claims written to {args.export}")
    if args.run:
        if not args.tag:
            parser.error("--run needs --tag")
        verdicts = judge_all(items, args.run, args.think, args.run_cap, args.workers, args.tag)
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"{args.tag}.jsonl").write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in verdicts))
        print(f"model {args.run}, thinking {args.think}, {sum('error' in v for v in verdicts)} errors")
        score(items, verdicts)
    if args.score:
        score(items, labelsheet.read_rows(args.score))


if __name__ == "__main__":
    main()
