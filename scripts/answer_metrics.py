"""Metrics of a pilot run of the answer path (step 0d): faithfulness (the claim judge of decision 16 on every claim),
citations and refusals counted from the pilot file. Spends model money for the judge unless --reuse finds its file.
  uv run python scripts/answer_metrics.py --tag flash-v3
"""

import argparse
import json
from pathlib import Path

from legalrag import answermetrics, claimjudge, gold, labelsheet

PILOT = Path("data/pilot")
JUDGE = Path("data/judge")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tag", required=True, help="the pilot file data/pilot/answers_<tag>.jsonl")
    parser.add_argument("--model", default="deepseek-flash")
    parser.add_argument("--prompt", default="judge.v2")
    parser.add_argument("--run-cap", type=float, default=0.5)
    parser.add_argument("--reuse", action="store_true", help="use the verdicts file of an earlier run")
    args = parser.parse_args()

    questions = {q.id: q.question for q in gold.load_gold(Path("eval/gold.jsonl"))}
    rows = [{**r, "question": questions[r["id"]]} for r in labelsheet.read_rows(PILOT / f"answers_{args.tag}.jsonl")]
    verdict_file = JUDGE / f"answers-{args.tag}.jsonl"
    if args.reuse and verdict_file.exists():
        verdicts = labelsheet.read_rows(verdict_file)
    else:
        items = answermetrics.claim_items(rows)
        verdicts = claimjudge.run_judge(items, args.model, False, args.run_cap, 6, f"answers-{args.tag}", args.prompt)
        JUDGE.mkdir(parents=True, exist_ok=True)
        verdict_file.write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in verdicts))
    result = {"tag": args.tag, "judge": {"model": args.model, "prompt": args.prompt},
              "faithfulness": answermetrics.faithfulness(verdicts), "citations": answermetrics.citations(rows),
              "refusals": answermetrics.refusals(rows), "passages": answermetrics.passages(rows),
              "cost": answermetrics.cost(rows)}
    (PILOT / f"metrics_{args.tag}.json").write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result, indent=1))
    claims = {f"{r['id']}|claim{i}": c.text for r in rows if r["outcome"] == "answered"
              for i, c in enumerate(labelsheet.parse_answer(r["text"]))}
    print("\nclaims the judge marks not supported:")
    for v in verdicts:
        if v.get("label") == "not supported":
            print(f"\n{v['key']}: {claims[v['key']]}\n  {v['reason']}")


if __name__ == "__main__":
    main()
