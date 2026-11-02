"""Pilot of the LLM-written heading sentence (step 0c): the same 50 articles through one backend.

  --backend local     an OpenAI-compatible server (llama-server) at --base-url; free, measures speed
  --backend deepseek  deepseek-flash through llm.py (cost ledger and caps); about 0.01 USD for 50 articles
Output: one JSON line per article (no article text) and a summary on screen. See
docs/handoff/local_llm_windows.md for the local run.
"""

import argparse
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from legalrag import headsentence, llm
from legalrag import questiongen as qg
from legalrag.sources import gdpr, legi

RAW = Path("data/raw")
PROMPT_IDS = ("sentence.v1", "sentence.v2", "sentence.v3")
SEED = 20261101


def load_articles():
    return legi.to_articles(legi.read(RAW / "legi_vincegx33_train.parquet")) + gdpr.parse(RAW / "gdpr_fr.xhtml", "fr")


def ask_deepseek(http, budget, tag, model, article, chat, max_tokens) -> dict:
    started = time.monotonic()
    text = llm.chat(http, llm.LEDGER, budget, f"{tag}-{article.uid}", model, chat, max_tokens,
                    thinking=False, json_mode=False, temperature=0)
    return {"text": text, "seconds": round(time.monotonic() - started, 3), "usage": None, "timings": None}


def git_state() -> dict:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True).stdout)
    except (OSError, subprocess.CalledProcessError):
        return {"git_commit": None, "uncommitted_changes": None}
    return {"git_commit": commit, "uncommitted_changes": dirty}


def server_info(http: httpx.Client) -> dict | None:
    """Build, slots and context size from /props (llama-server); None when it reports nothing. Only these
    fields are kept: the full reply holds the model's file path, and the output file is committed."""
    try:
        response = http.get("/props")
        response.raise_for_status()
        props = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    return {"build_info": props.get("build_info"), "total_slots": props.get("total_slots"),
            "n_ctx": (props.get("default_generation_settings") or {}).get("n_ctx")}


def summarize(records: list[dict], wall: float) -> str:
    done = [r for r in records if "error" not in r]
    flagged = {}
    for r in done:
        for flag in r["flags"]:
            flagged[flag] = flagged.get(flag, 0) + 1
    out_tokens = sum((r["usage"] or {}).get("completion_tokens", 0) for r in done)
    speeds = [r["timings"]["predicted_per_second"] for r in done if r.get("timings") and "predicted_per_second" in r["timings"]]
    lines = [f"{len(done)}/{len(records)} answered, {len(records) - len(done)} errors; flags {flagged or 'none'}",
             f"wall time {wall:.1f} s, mean {wall / max(len(records), 1):.2f} s per article (all workers together)",
             f"mean seconds per call {sum(r['seconds'] for r in done) / max(len(done), 1):.2f}"]
    if out_tokens:
        lines.append(f"{out_tokens} output tokens, {out_tokens / wall:.1f} tokens/s over the whole run")
    if speeds:
        lines.append(f"server decode speed per call: mean {sum(speeds) / len(speeds):.1f} tokens/s")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--backend", choices=("local", "deepseek"), required=True)
    parser.add_argument("--prompt", choices=PROMPT_IDS, default="sentence.v1")
    parser.add_argument("--model", required=True, help="local: the name the server reports; deepseek: deepseek-flash")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080", help="local server")
    parser.add_argument("--n", type=int, default=None, help="use only the first N of the 50 (trial)")
    parser.add_argument("--workers", type=int, default=1, help="calls in flight (local: match the server --parallel)")
    parser.add_argument("--run-cap", type=float, default=0.2, help="deepseek: USD this run may spend")
    parser.add_argument("--tag", required=True, help="names the output file and the ledger labels")
    parser.add_argument("--out-dir", type=Path, default=Path("data/pilot"))
    args = parser.parse_args()

    prompt = qg.load_prompts(Path("prompts/heading_sentence.yaml"))["prompts"][args.prompt]
    articles = headsentence.sample(load_articles(), SEED)[: args.n]
    jobs = [(a, headsentence.messages(prompt, a)) for a in articles]
    print(f"{len(jobs)} articles, prompt {args.prompt}, backend {args.backend}, workers {args.workers}")

    if args.backend == "deepseek":
        budget = llm.Budget(run_cap=args.run_cap, total_cap=5.0)
        http = llm.make_http(os.environ["DEEPSEEK_API_KEY"])
        llm.record_balance(llm.LEDGER, llm.balance(http), f"before-{args.tag}")

        def ask(job):
            return ask_deepseek(http, budget, args.tag, args.model, job[0], job[1], prompt["max_tokens"])
    else:
        http = httpx.Client(base_url=args.base_url, timeout=600)
        info = server_info(http)

        def ask(job):
            return headsentence.ask_local(http, args.model, job[1], prompt["max_tokens"])

    def one(job) -> dict:
        article = job[0]
        record = {"uid": article.uid, "source": article.source_code, "kind": article.kind,
                  "body_chars": len(article.body_text)}
        try:
            answer = ask(job)
        except (httpx.HTTPError, ValueError, KeyError, llm.BudgetExceeded) as error:
            return {**record, "error": f"{type(error).__name__}: {error}"}
        sentence, flags = headsentence.clean(answer["text"], prompt["max_words"])
        return {**record, "sentence": sentence, "flags": flags, "seconds": answer["seconds"],
                "usage": answer["usage"], "timings": answer["timings"]}

    started = time.monotonic()
    with ThreadPoolExecutor(args.workers) as pool:
        records = list(pool.map(one, jobs))
    wall = time.monotonic() - started
    if args.backend == "deepseek":
        llm.record_balance(llm.LEDGER, llm.balance(http), f"after-{args.tag}")
        info = {"cost_usd": round(sum(e["cost_usd"] for e in llm.read_ledger(llm.LEDGER)
                                       if e["type"] == "call" and e["label"].startswith(f"{args.tag}-")), 5)}

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"heading_{args.tag}.jsonl"
    header = {"type": "run", "prompt": args.prompt, "seed": SEED, "backend": args.backend, "model": args.model,
              "workers": args.workers, "wall_seconds": round(wall, 2), "server": info, **git_state()}
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [header, *records]) + "\n")
    print(summarize(records, wall))
    if args.backend == "deepseek":
        print(f"cost {info['cost_usd']} USD (ledger)")
    print(f"written {out}")


if __name__ == "__main__":
    main()
