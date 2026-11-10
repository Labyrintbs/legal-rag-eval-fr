"""Write the sheet for labelling answers by hand (step 0d): `data/labels/<tag>.html` from a pilot file.
Open it in a browser, label, press "Download labels.json" and move the file to `data/labels/<tag>.labels.json`.
"""

import argparse
import json
from pathlib import Path

from legalrag import db, embed, gold, labelsheet, rag
from legalrag.labels import split_label

PILOT = Path("data/pilot")
OUT = Path("data/labels")
RUN = "default"  # the chunking run of the pilot


def add_context(rows: list[dict]) -> list[dict]:
    """For the refusals: the articles the model was shown (the same search as the pilot) and the gold articles' text,
    so that a refusal can be judged."""
    todo = [r for r in rows if r["outcome"] != "answered"]
    if not todo:
        return rows
    with db.connect() as conn:
        run_id = conn.execute("SELECT id FROM chunking_runs WHERE name = %s", (RUN,)).fetchone()[0]
        retriever = rag.LegalRetriever(db.connect, run_id, embed.SentenceTransformerEmbedder("cpu"), "fr")
        for r in todo:
            r["seen"] = [(n.node.metadata["label"], n.node.text) for n in retriever.retrieve(r["question"])]
            r["gold_text"] = []
            for label in r["gold"]:
                source, kind, num = split_label(label)
                found = conn.execute(
                    "SELECT body_text FROM articles WHERE source_code = %s AND kind = %s AND article_num = %s AND lang = 'fr' "
                    "ORDER BY valid_from DESC LIMIT 1", (source, kind, num)).fetchone()
                if found:
                    r["gold_text"].append((label, found[0]))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="flash-v3", help="the pilot file data/pilot/answers_<tag>.jsonl")
    parser.add_argument("--answered", type=int, default=19, help="plain answers to sample, besides every refusal")
    parser.add_argument("--name", help="sheet name (default: the tag)")
    parser.add_argument("--skip-labels", type=Path, help="a downloaded labels.json: its answers are left out")
    parser.add_argument("--checks", type=Path, help="claim checks to add, e.g. eval/answer_checks.json")
    args = parser.parse_args()

    name = args.name or args.tag
    questions = {q.id: q.question for q in gold.load_gold(Path("eval/gold.jsonl"))}
    rows = [{**r, "question": questions[r["id"]]} for r in labelsheet.read_rows(PILOT / f"answers_{args.tag}.jsonl")]
    done = {key.split("|")[0] for key in json.loads(args.skip_labels.read_text())["labels"]} if args.skip_labels else set()
    sample = add_context(labelsheet.pick(rows, args.answered, skip=frozenset(done)))
    checks = labelsheet.load_checks(args.checks, rows) if args.checks else []
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.html"
    path.write_text(labelsheet.render(sample, name, checks))
    claims = sum(len(labelsheet.parse_answer(r["text"])) for r in sample if r["outcome"] == "answered") + len(checks)
    print(f"{len(sample)} answers and {len(checks)} claim checks ({claims} claims to label) written to {path}")


if __name__ == "__main__":
    main()
