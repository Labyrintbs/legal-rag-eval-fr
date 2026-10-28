"""Build the draft gold file from the smoke questions and the kept model-written questions.

Reads data/questions/model_written.json and tests/smoke_questions.yaml, takes each gold article's
content hash from the database, and writes data/gold/draft.jsonl. No API call.
Smoke questions list articles without grades: all become primary and a list of several is marked
needs_review.
"""

import json
from pathlib import Path

from legalrag import db, gold
from legalrag.smoke import load_questions

MODEL_WRITTEN = Path("data/questions/model_written.json")
SMOKE = Path("tests/smoke_questions.yaml")
OUT = Path("data/gold/draft.jsonl")
# Plain questions are lookups (group A); lay ones are the wording gap (group B).
STYLE_GROUP = {"plain": "A", "lay": "B"}
SMOKE_KINDS = {26: "false_premise", 27: "underspecified", 28: "unanswerable", 29: "unanswerable"}


def source_of(label: str) -> str:
    return "rgpd" if label.startswith(("art ", "rct ")) else "code_travail"


def gold_article(label: str, lang: str, hashes: dict) -> gold.GoldArticle:
    source = source_of(label)
    # Code du travail exists in French only; the GDPR text is taken in the question's language.
    article_lang = lang if source == "rgpd" else "fr"
    found = hashes[(source, label, article_lang)]
    if len(found) != 1:
        raise ValueError(f"{label} ({article_lang}): {len(found)} matching articles")
    return gold.GoldArticle(source=source, article=label, lang=article_lang, grade=gold.GRADE_PRIMARY,
                            content_hash=next(iter(found)))


def model_written(hashes: dict) -> list[gold.GoldQuestion]:
    questions = []
    for r in json.loads(MODEL_WRITTEN.read_text()):
        if not r["keep"]:
            continue
        label = r["article"] if r["source"] == "code_travail" else f"art {r['article']}"
        questions.append(gold.GoldQuestion(
            id=r["id"], question=r["question"], lang="fr", group=STYLE_GROUP[r["style"].split(".")[0]],
            kind="answerable", gold=[gold_article(label, "fr", hashes)],
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
    for q in load_questions(SMOKE):
        articles = [gold_article(label, q.lang, hashes) for label in q.expected]
        questions.append(gold.GoldQuestion(
            id=f"smoke-{q.id:02d}", question=q.question, lang=q.lang, group=q.group,
            kind=SMOKE_KINDS.get(q.id, "answerable"), gold=articles,
            provenance=gold.Provenance(method="smoke", date="2026-10-22"),
            review=gold.Review(note=q.note, status="needs_review" if len(articles) > 1 else "checked"),
        ))
    return questions


def main() -> None:
    with db.connect() as conn:
        hashes = gold.article_hashes(conn)
    questions = model_written(hashes) + smoke(hashes)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    gold.write_gold(OUT, questions)
    print(f"written {OUT}: {len(questions)} questions")


if __name__ == "__main__":
    main()
