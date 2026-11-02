"""Heading sentences for the whole corpus (step 0c): deepseek-flash writes one question per article, French
prompt `sentence.v3` for French articles and `sentence.v3.en` for the English GDPR. Resumable: articles
already in the output file are skipped, so `--limit 200` is the first part of the full run, not a throwaway.
Output: data/sentences/heading-sentences-v3.jsonl (uid, lang, sentence, flags); articles with an unusable
sentence keep the plain heading (headsentence.UNUSABLE). Run with --dry-run first: it spends nothing.
"""

import argparse
import json
import os
import random
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from legalrag import headsentence, llm
from legalrag import questiongen as qg
from legalrag.sources import gdpr, legi

RAW = Path("data/raw")
MODEL = "deepseek-flash"
OUT = Path("data/sentences/heading-sentences-v3.jsonl")
SEED = 20261103
# Cost per article seen in the 50-article pilots (0.0046 to 0.0051 USD for 50), for the dry-run estimate.
PILOT_USD_PER_ARTICLE = 0.0001


def corpus() -> list:
    return (legi.to_articles(legi.read(RAW / "legi_vincegx33_train.parquet"))
            + gdpr.parse(RAW / "gdpr_fr.xhtml", "fr") + gdpr.parse(RAW / "gdpr_en.xhtml", "en"))


def done_uids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {r["uid"] for r in (json.loads(line) for line in path.read_text().splitlines() if line.strip())
            if r.get("type") != "run"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--limit", type=int, default=None, help="only this many of the articles still to do")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--run-cap", type=float, default=2.0, help="USD this invocation may spend")
    parser.add_argument("--dry-run", action="store_true", help="count, estimate the cost, send nothing")
    args = parser.parse_args()

    prompts = qg.load_prompts(Path("prompts/heading_sentence.yaml"))["prompts"]
    articles = corpus()
    already = done_uids(args.out)
    pending = [a for a in articles if a.uid not in already]
    random.Random(SEED).shuffle(pending)  # a --limit trial then covers every kind and language
    pending = pending[: args.limit]
    jobs = [(a, headsentence.messages(prompts[headsentence.PROMPT_BY_LANG[a.lang]], a)) for a in pending]
    worst = sum(llm.worst_case_cost(MODEL, llm.estimate_tokens("".join(m["content"] for m in chat)),
                                    prompts[headsentence.PROMPT_BY_LANG[a.lang]]["max_tokens"]) for a, chat in jobs)
    print(f"{len(articles)} articles, {len(already)} done, {len(jobs)} to do now; expected about "
          f"{len(jobs) * PILOT_USD_PER_ARTICLE:.2f} USD (pilot rate), worst case {worst:.2f} USD, run cap {args.run_cap}")
    if args.dry_run or not jobs:
        return

    budget = llm.Budget(run_cap=args.run_cap, total_cap=5.0)
    http = llm.make_http(os.environ["DEEPSEEK_API_KEY"])
    spent_before = llm.ledger_total(llm.LEDGER)
    llm.record_balance(llm.LEDGER, llm.balance(http), "before-sentences-v3")

    def one(job) -> dict | None:
        article, chat = job
        prompt = prompts[headsentence.PROMPT_BY_LANG[article.lang]]
        try:
            text = llm.chat(http, llm.LEDGER, budget, f"sentences-v3-{article.uid}", MODEL, chat, prompt["max_tokens"],
                            thinking=False, json_mode=False, temperature=0)
        except (httpx.HTTPError, ValueError, KeyError, llm.BudgetExceeded):
            return None  # not written, so a rerun tries it again
        sentence, flags = headsentence.clean(text, prompt["max_words"])
        return {"uid": article.uid, "lang": article.lang, "kind": article.kind, "sentence": sentence, "flags": flags}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    started = time.monotonic()
    written = failed = 0
    with args.out.open("a") as f, ThreadPoolExecutor(args.workers) as pool:
        f.write(json.dumps({"type": "run", "model": MODEL, "prompts": headsentence.PROMPT_BY_LANG, "git_commit": commit,
                            "jobs": len(jobs)}) + "\n")
        for result in pool.map(one, jobs):
            if result is None:
                failed += 1
                continue
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
            f.flush()
            written += 1
    llm.record_balance(llm.LEDGER, llm.balance(http), "after-sentences-v3")
    spent = llm.ledger_total(llm.LEDGER) - spent_before
    rows = [json.loads(line) for line in args.out.read_text().splitlines() if line.strip()]
    flags = {}
    for r in rows:
        for flag in r.get("flags", []):
            flags[flag] = flags.get(flag, 0) + 1
    print(f"{written} written, {failed} failed (rerun to retry), {time.monotonic() - started:.0f} s, {spent:.4f} USD; "
          f"file now holds {len(rows) - sum(r.get('type') == 'run' for r in rows)} articles, flags {flags}")


if __name__ == "__main__":
    main()
