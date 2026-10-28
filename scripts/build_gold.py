"""Build the draft gold file from the smoke questions and the kept model-written questions.

Reads data/questions/model_written.json, data/questions/sheet_questions.json, data/questions/handwritten.json and tests/smoke_questions.yaml, takes each gold article's
content hash from the database, assigns the dev/test split, and writes eval/gold.jsonl. No API call.
Smoke questions list articles without grades: the assistant's proposed grades (smoke_grades.json,
null drops an article) are applied and every list of several stays needs_review until the user checks.
"""

import json
from pathlib import Path

from legalrag import db, gold
from legalrag.smoke import load_questions

MODEL_WRITTEN = Path("data/questions/model_written.json")
SHEETS = Path("data/questions/sheet_questions.json")
HANDWRITTEN = Path("data/questions/handwritten.json")
SMOKE_GRADES = Path("data/questions/smoke_grades.json")
SMOKE = Path("tests/smoke_questions.yaml")
OUT = Path("eval/gold.jsonl")
# Plain questions are lookups (group A); lay ones are the wording gap (group B); conditions ones
# ask about a condition or exception (new group H).
STYLE_GROUP = {"plain": "A", "lay": "B", "conditions": "H"}
SMOKE_KINDS = {26: "false_premise", 27: "underspecified", 28: "unanswerable", 29: "unanswerable"}


def source_of(label: str) -> str:
    return "rgpd" if label.startswith(("art ", "rct ")) else "code_travail"


def gold_article(label: str, lang: str, hashes: dict, grade: int = gold.GRADE_PRIMARY) -> gold.GoldArticle:
    source = source_of(label)
    # Code du travail exists in French only; the GDPR text is taken in the question's language.
    article_lang = lang if source == "rgpd" else "fr"
    found = hashes[(source, label, article_lang)]
    if len(found) != 1:
        raise ValueError(f"{label} ({article_lang}): {len(found)} matching articles")
    return gold.GoldArticle(source=source, article=label, lang=article_lang, grade=grade,
                            content_hash=next(iter(found)))


def model_written(hashes: dict) -> list[gold.GoldQuestion]:
    questions = []
    for r in json.loads(MODEL_WRITTEN.read_text()):
        if not r["keep"]:
            continue
        label = r["article"] if r["source"] == "code_travail" else f"art {r['article']}"
        questions.append(gold.GoldQuestion(
            id=r["id"], question=r["question"], lang="fr", group=STYLE_GROUP[r["style"].split(".")[0]],
            kind="answerable",
            gold=[gold_article(label, "fr", hashes)]
            + [gold_article(extra, "fr", hashes, grade) for extra, grade in r.get("extra_gold", {}).items()],
            provenance=gold.Provenance(method="model_written", writer=r["writer"], style=r["style"],
                                       prompt_hash=r["prompt_hash"], reviewer=r["reviewer_id"],
                                       date="2026-10-27"),
            review=gold.Review(pipeline=r["pipeline"], audit=r["audit"], by="assistant",
                               note=r["audit_reason"]),
            answer=gold.Answer(short=r["short_answer"]),
        ))
    return questions


def smoke(hashes: dict) -> list[gold.GoldQuestion]:
    questions = []
    grades = json.loads(SMOKE_GRADES.read_text())
    for q in load_questions(SMOKE):
        proposal = grades.get(str(q.id), {})
        # A null grade drops a background article; no proposal means all expected articles stay primary.
        articles = [gold_article(label, q.lang, hashes, proposal.get(label, gold.GRADE_PRIMARY))
                    for label in q.expected if proposal.get(label, 1) is not None]
        questions.append(gold.GoldQuestion(
            id=f"smoke-{q.id:02d}", question=q.question, lang=q.lang, group=q.group,
            kind=SMOKE_KINDS.get(q.id, "answerable"), gold=articles,
            provenance=gold.Provenance(method="smoke", date="2026-10-22"),
            review=gold.Review(note=" | ".join(filter(None, [q.note, proposal.get("note", "")])),
                               by="assistant" if proposal else None,
                               status=proposal.get("status", "needs_review" if len(q.expected) > 1 else "checked")),
        ))
    return questions


def sheets(hashes: dict) -> list[gold.GoldQuestion]:
    """Questions worded from the ministry sheet headings; the audited gold is in SHEETS (not committed)."""
    questions = []
    for r in json.loads(SHEETS.read_text()):
        questions.append(gold.GoldQuestion(
            id=r["id"], question=r["question"], lang="fr", group="I", kind="answerable",
            gold=[gold_article(g["article"], "fr", hashes, g["grade"]) for g in r["gold"]],
            provenance=gold.Provenance(method="ministry_sheet", source_url=r["url"], source_heading=r["heading"],
                                       gold_origin=r["gold_origin"], date="2026-10-28"),
            review=gold.Review(audit="accept", by="assistant", note=r["note"], status=r["status"]),
        ))
    return questions


def handwritten(hashes: dict) -> list[gold.GoldQuestion]:
    """Cross-source, false-premise, unanswerable and underspecified questions written by the assistant."""
    return [
        gold.GoldQuestion(
            id=r["id"], question=r["question"], lang="fr", group=r["group"], kind=r["kind"],
            gold=[gold_article(g["article"], "fr", hashes, g["grade"]) for g in r["gold"]],
            provenance=gold.Provenance(method="hand_written", writer="assistant", date="2026-10-28"),
            review=gold.Review(by="assistant", note=r["note"], status=r["status"]),
        )
        for r in json.loads(HANDWRITTEN.read_text())
    ]


def main() -> None:
    with db.connect() as conn:
        hashes = gold.article_hashes(conn)
    questions = model_written(hashes) + sheets(hashes) + handwritten(hashes) + smoke(hashes)
    split = gold.assign_split(questions)
    for q in questions:
        q.split = split[q.id]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    gold.write_gold(OUT, questions)
    print(f"written {OUT}: {len(questions)} questions")


if __name__ == "__main__":
    main()
