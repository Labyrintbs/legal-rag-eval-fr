"""Write the sheet for labelling answers by hand (step 0d): `data/labels/<tag>.html` from a pilot file.
Open it in a browser, label, press "Download labels.json" and move the file to `data/labels/<tag>.labels.json`.
"""

import argparse
from pathlib import Path

from legalrag import gold, labelsheet

PILOT = Path("data/pilot")
OUT = Path("data/labels")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="flash-v3", help="the pilot file data/pilot/answers_<tag>.jsonl")
    parser.add_argument("--answered", type=int, default=19, help="plain answers to sample, besides every refusal")
    args = parser.parse_args()

    questions = {q.id: q.question for q in gold.load_gold(Path("eval/gold.jsonl"))}
    rows = [{**r, "question": questions[r["id"]]} for r in labelsheet.read_rows(PILOT / f"answers_{args.tag}.jsonl")]
    sample = labelsheet.pick(rows, args.answered)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{args.tag}.html"
    path.write_text(labelsheet.render(sample, args.tag))
    claims = sum(len(labelsheet.parse_answer(r["text"])) for r in sample if r["outcome"] == "answered")
    print(f"{len(sample)} answers ({claims} claims to label) written to {path}")


if __name__ == "__main__":
    main()
