"""Write the sheet for the hand check of completeness (decision 19): 20 pairs of (reference claim, our answer) from the
`full` English run, a sample chosen by the judge's label but shown without it. Open data/labels/completeness.html in a
browser, label, press "Download labels.json" and move the file to data/labels/completeness.labels.json.
  uv run python scripts/make_completeness_sheet.py
"""

import json
from pathlib import Path

from legalrag.evaluation import claimrag, labelsheet

DATA = Path("data/claimrag")
OUT = Path("data/labels")
COUNTS = {"supported": 7, "partly": 6, "not supported": 7}  # by the judge's label, so that all three kinds are checked


def main() -> None:
    rows = labelsheet.read_rows(DATA / "answers_full.jsonl")
    verdicts = labelsheet.read_rows(Path("data/judge/claimrag-english-full-complete.jsonl"))
    picked = claimrag.pick_pairs(claimrag.completeness_items(rows), verdicts, COUNTS)
    by_id = {r["id"]: r for r in rows}
    pairs = []
    for item in picked:
        row = by_id[int(item.key.split("|")[0])]
        answer = "\n".join(c.text for c in labelsheet.parse_answer(row["text"]))
        pairs.append((item.key, row["question"], item.claim, answer))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "completeness.html").write_text(labelsheet.render_pairs(pairs, "completeness"))
    (OUT / "completeness.sample.json").write_text(json.dumps([i.key for i in picked]))
    print(f"{len(pairs)} pairs from {len({i.key.split('|')[0] for i in picked})} questions written to {OUT / 'completeness.html'}")


if __name__ == "__main__":
    main()
