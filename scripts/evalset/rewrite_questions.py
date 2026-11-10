"""Query rewriting (step 0c): deepseek-flash restates each question of one half in the wording of the code.
Output: data/rewrites/<tag>_<split>.jsonl, one line per question (the first line describes the run).
The test half needs --final, as for `legalrag eval`.
"""

import argparse
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from legalrag import llm
from legalrag.evaluation import gold
from legalrag.evaluation import questiongen as qg
from legalrag.experiments import rewrite

PROMPT_ID = "rewrite.v1"
MODEL = "deepseek-flash"
OUT = Path("data/rewrites")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", default="dev", choices=("dev", "test"))
    parser.add_argument("--final", action="store_true", help="allow the test half (decision 5)")
    parser.add_argument("--file", type=Path, default=Path("eval/gold.jsonl"))
    parser.add_argument("--n", type=int, default=None, help="trial: only the first N questions")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--run-cap", type=float, default=0.1, help="USD this run may spend")
    parser.add_argument("--tag", default=PROMPT_ID)
    args = parser.parse_args()
    if args.split == "test" and not args.final:
        parser.error("the test half is for the end of a stage: add --final")

    prompt = qg.load_prompts(Path("prompts/query_rewrite.yaml"))["prompts"][PROMPT_ID]
    questions = [q for q in gold.load_gold(args.file) if q.split == args.split][: args.n]
    budget = llm.Budget(run_cap=args.run_cap, total_cap=5.0)
    http = llm.make_http(os.environ["DEEPSEEK_API_KEY"])
    llm.record_balance(llm.LEDGER, llm.balance(http), f"before-rewrite-{args.tag}")

    def one(q) -> dict:
        record = {"id": q.id, "question": q.question}
        started = time.monotonic()
        try:
            text = llm.chat(http, llm.LEDGER, budget, f"rewrite-{args.tag}-{q.id}", MODEL,
                            rewrite.messages(prompt, q.question), prompt["max_tokens"],
                            thinking=False, json_mode=False, temperature=0)
        except (httpx.HTTPError, ValueError, KeyError, llm.BudgetExceeded) as error:
            return {**record, "rewrite": "", "flags": ["error"], "used": q.question, "error": f"{type(error).__name__}: {error}"}
        text, flags = rewrite.clean(text, prompt["max_words"])
        return {**record, "rewrite": text, "flags": flags, "used": rewrite.used_text(q.question, text, flags),
                "seconds": round(time.monotonic() - started, 3)}

    with ThreadPoolExecutor(args.workers) as pool:
        rows = list(pool.map(one, questions))
    llm.record_balance(llm.LEDGER, llm.balance(http), f"after-rewrite-{args.tag}")
    cost = sum(e["cost_usd"] for e in llm.read_ledger(llm.LEDGER)
               if e["type"] == "call" and e["label"].startswith(f"rewrite-{args.tag}-"))
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    header = {"type": "run", "prompt": PROMPT_ID, "model": MODEL, "split": args.split, "git_commit": commit,
              "cost_usd": round(cost, 5)}
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{args.tag}_{args.split}.jsonl"
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [header, *rows]) + "\n")
    flagged = [r for r in rows if r["flags"]]
    changed = sum(r["used"] != r["question"] for r in rows)
    print(f"{len(rows)} questions, {changed} searched with a rewrite, {len(flagged)} flagged "
          f"({[(r['id'], r['flags']) for r in flagged]}), cost {cost:.5f} USD")
    print(f"written {path}")


if __name__ == "__main__":
    main()
