"""Ministry check (step 0f): for the questions taken from a sheet of the ministry of labour, does our answer contradict the
ministry's own text under the same heading? Dev half first; the sheets are the local file data/external/fiches-travail.json.
Writes the verdicts `data/judge/ministry-<tag>.jsonl` and a label sheet `data/labels/ministry-<tag>.html` with the official
text, for the hand check. Spends under a cent of DeepSeek money.
  uv run --env-file .env python scripts/answers/ministry_check.py --tag flash-v3 --split dev
"""

import argparse
import json
import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from legalrag import llm
from legalrag.evaluation import gold, judgecall, labelsheet, ministry
from legalrag.evaluation.questiongen import load_prompts

MODEL = "deepseek-flash"
SHEETS = Path("data/external/fiches-travail.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tag", default="flash-v3", help="the pilot file data/pilot/answers_<tag>.jsonl")
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument("--run-cap", type=float, default=0.1, help="most USD this run may spend")
    parser.add_argument("--prompt", default="ministry_check.v1", help="a prompt id of prompts/ministry_check.yaml")
    args = parser.parse_args()
    stem = f"ministry-{args.tag}" + ("" if args.prompt == "ministry_check.v1" else f"-{args.prompt.split('.')[-1]}")

    sheets = ministry.load_sheets(SHEETS)
    asked = {q.id: q for q in gold.load_gold(Path("eval/gold.jsonl"))
             if q.provenance.method == "ministry_sheet" and q.split == args.split and q.lang == "fr"}
    rows = {r["id"]: r for r in labelsheet.read_rows(Path("data/pilot") / f"answers_{args.tag}.jsonl")}
    items, refused = {}, []
    for qid, q in asked.items():
        official = ministry.official_text(sheets, q.provenance.source_url, q.provenance.source_heading)
        if official is None:
            raise SystemExit(f"{qid}: no section of the sheet matches the heading {q.provenance.source_heading!r}")
        if rows[qid]["outcome"] != "answered":
            refused.append((qid, rows[qid]["outcome"]))
            continue
        items[qid] = (q.question, "\n".join(c.text for c in labelsheet.parse_answer(rows[qid]["text"])), official)

    prompt = load_prompts(Path("prompts/ministry_check.yaml"))["prompts"][args.prompt]
    budget = llm.Budget(run_cap=args.run_cap, total_cap=5.0)
    with llm.make_http(os.environ["DEEPSEEK_API_KEY"]) as http, ThreadPoolExecutor(6) as pool:
        jobs = {qid: pool.submit(judgecall.ask, http, budget, stem, MODEL,
                                 judgecall.chat_messages(prompt, question=q, official=official, answer=answer),
                                 prompt["max_tokens"], ministry.Verdict) for qid, (q, answer, official) in items.items()}
        results = {qid: job.result() for qid, job in jobs.items()}
    out = [{"key": qid, **({"label": r["value"].label, "reason": r["value"].reason} if "value" in r else {"error": r["error"]})}
           for qid, r in results.items()]
    Path("data/judge").mkdir(parents=True, exist_ok=True)
    (Path("data/judge") / f"{stem}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out))
    print(f"{len(asked)} ministry questions in {args.split}: {len(items)} answered, refused: {refused}")
    print("judge:", dict(Counter(r.get("label", "error") for r in out)))
    for r in out:
        if r.get("label") != "agrees":
            print(f"\n{r['key']}: {r.get('label')} - {r.get('reason', r.get('error'))}")
    Path("data/labels").mkdir(parents=True, exist_ok=True)
    sheet = labelsheet.render_ministry([(qid, q, answer, official) for qid, (q, answer, official) in items.items()], stem)
    (Path("data/labels") / f"{stem}.html").write_text(sheet)
    print(f"\nsheet: data/labels/{stem}.html")


if __name__ == "__main__":
    main()
