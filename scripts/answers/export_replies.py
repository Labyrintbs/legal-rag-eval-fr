"""Exports the model replies of an answer pilot run on the dev half to tests/fixtures/replies_dev.json, for the
answer-path replay of the quality gate (step 0e). Keeps what the replay checks: the raw reply, the outcome and the cited articles.
"""

import argparse
import json
from pathlib import Path

OUT = Path("tests/fixtures/replies_dev.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tag", default="flash-v3", help="the run data/pilot/answers_<tag>.jsonl (dev half, final settings)")
    args = parser.parse_args()
    rows = [json.loads(line) for line in Path(f"data/pilot/answers_{args.tag}.jsonl").read_text().splitlines()]
    replies = {r["id"]: {"raw": r["raw"], "outcome": r["outcome"], "cited": r["cited"]} for r in rows}
    OUT.write_text(json.dumps({"source": f"answers_{args.tag}.jsonl", "replies": replies}, ensure_ascii=False, indent=1) + "\n")
    print(f"{len(replies)} replies, {OUT.stat().st_size / 1e3:.0f} kB")


if __name__ == "__main__":
    main()
