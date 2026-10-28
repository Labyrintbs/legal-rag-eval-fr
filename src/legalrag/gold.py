"""Gold file of the evaluation set: one JSON object per line, one question each (decision 14).

Article labels follow the smoke output: Code du travail article number (annexes: their full name),
GDPR "art N" or "rct N". Identical-body alternatives are not stored; they are computed at evaluation time.
"""

from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

import psycopg
from pydantic import BaseModel, model_validator

Kind = Literal["answerable", "unanswerable", "false_premise", "underspecified"]
Method = Literal["model_written", "ministry_sheet", "hand_written", "smoke"]
GRADE_PRIMARY, GRADE_ACCEPTABLE = 2, 1
ARTICLES = "SELECT source_code, kind, article_num, lang, content_hash FROM articles"


class GoldArticle(BaseModel):
    source: Literal["code_travail", "rgpd"]
    article: str
    lang: str
    grade: Literal[1, 2]
    content_hash: str


class Provenance(BaseModel):
    method: Method
    writer: str | None = None
    style: str | None = None
    prompt_hash: str | None = None
    reviewer: str | None = None
    source_url: str | None = None
    # Ministry sheets: the sheet's own heading, and who chose the gold articles.
    source_heading: str | None = None
    gold_origin: Literal["ministry", "assistant"] | None = None
    date: str | None = None


class Review(BaseModel):
    pipeline: str | None = None
    audit: Literal["accept", "borderline", "reject"] | None = None
    by: str | None = None
    note: str = ""
    # needs_review: a grade or an article the user has not confirmed (decision 2).
    status: Literal["checked", "needs_review"] = "checked"


class Answer(BaseModel):
    short: str | None = None
    key_facts: list[str] = []


class GoldQuestion(BaseModel):
    id: str
    question: str
    lang: str
    group: str
    kind: Kind
    gold: list[GoldArticle] = []
    split: Literal["dev", "test"] | None = None
    provenance: Provenance
    review: Review = Review()
    answer: Answer = Answer()

    @model_validator(mode="after")
    def gold_matches_kind(self):
        if self.kind == "unanswerable":
            if self.gold:
                raise ValueError(f"{self.id}: an unanswerable question has no gold")
            return self
        if not any(g.grade == GRADE_PRIMARY for g in self.gold):
            raise ValueError(f"{self.id}: needs at least one primary (grade 2) article")
        keys = [(g.source, g.article, g.lang) for g in self.gold]
        if len(set(keys)) != len(keys):
            raise ValueError(f"{self.id}: the same article is listed twice")
        return self


def load_gold(path: Path) -> list[GoldQuestion]:
    questions = [GoldQuestion.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()]
    ids = [q.id for q in questions]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate question id")
    return questions


def write_gold(path: Path, questions: Iterable[GoldQuestion]) -> None:
    path.write_text("".join(q.model_dump_json() + "\n" for q in questions))


def to_qrels(questions: Iterable[GoldQuestion]) -> list[tuple[str, str, int]]:
    """TREC qrels rows (query id, article label, grade). Unanswerable questions have none."""
    return [(q.id, g.article, g.grade) for q in questions for g in q.gold]


def format_qrels(rows: Iterable[tuple[str, str, int]]) -> str:
    """TREC lines `query_id 0 doc_id relevance`; labels have spaces ("art 17") so they are joined with `_`."""
    return "".join(f"{q} 0 {doc.replace(' ', '_')} {grade}\n" for q, doc, grade in rows)


def article_hashes(conn: psycopg.Connection) -> dict[tuple[str, str, str], set[str]]:
    """(source, label, lang) -> content hashes found in the database (more than one means ambiguous)."""
    hashes = defaultdict(set)
    for source, kind, num, lang, content_hash in conn.execute(ARTICLES):
        label = num if source == "code_travail" else f"{'art' if kind == 'article' else 'rct'} {num}"
        hashes[(source, label, lang)].add(content_hash)
    return hashes


def check_hashes(questions: Iterable[GoldQuestion], hashes: dict[tuple[str, str, str], set[str]]) -> list[str]:
    """Problems: a gold article missing from the database, changed since it was labelled, or ambiguous."""
    problems = []
    for q in questions:
        for g in q.gold:
            found = hashes.get((g.source, g.article, g.lang), set())
            where = f"{q.id}: {g.source} {g.article} ({g.lang})"
            if not found:
                problems.append(f"{where} is not in the database")
            elif len(found) > 1:
                problems.append(f"{where} matches {len(found)} different articles")
            elif g.content_hash not in found:
                problems.append(f"{where} changed since it was labelled")
    return problems
