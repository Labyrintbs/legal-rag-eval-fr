"""Blind second opinion on gold lists: a model grades candidate articles without knowing the gold."""

import random
from dataclasses import dataclass

from legalrag.gold import GoldQuestion

TEXT_CHARS = 3000
KINDS = {"answerable", "false_premise", "underspecified", "unanswerable"}


@dataclass
class Candidate:
    id: str
    label: str
    context: str
    text: str


def shuffled_candidates(labels: list[str], texts: dict[str, tuple[str, str]], seed: str) -> list[Candidate]:
    """Gold and retrieved articles in a random order, so position does not reveal which is gold.
    texts maps a label to (section context, article text)."""
    order = sorted(set(labels))
    random.Random(seed).shuffle(order)
    return [Candidate(f"A{i}", label, texts[label][0], texts[label][1][:TEXT_CHARS])
            for i, label in enumerate(order, 1)]


def judge_messages(prompts: dict, judge: str, question: str, candidates: list[Candidate]) -> list[dict]:
    listing = "\n\n".join(f"{c.id}\nContexte : {c.context}\nTexte : {c.text}" for c in candidates)
    user = f"Question : {question}\n\nArticles candidats :\n\n{listing}"
    return [{"role": "system", "content": prompts["judges"][judge]["system"]}, {"role": "user", "content": user}]


def grades_by_label(verdict: dict | None, candidates: list[Candidate]) -> dict[str, int] | None:
    """The judge's grade per article label, or None when the verdict is missing a candidate or a grade."""
    if not verdict or "error" in verdict:
        return None
    given = {a.get("id"): a.get("grade") for a in verdict.get("articles", []) if isinstance(a, dict)}
    if any(given.get(c.id) not in (0, 1, 2) for c in candidates):
        return None
    return {c.label: given[c.id] for c in candidates}


def compare(question: GoldQuestion, verdict: dict | None, candidates: list[Candidate]) -> dict:
    """Where the judge and the gold differ: grades on gold articles, extra articles the judge accepts,
    and the question kind."""
    judged = grades_by_label(verdict, candidates)
    if judged is None:
        return {"id": question.id, "failed": True}
    gold = {g.article: g.grade for g in question.gold}
    kind = verdict.get("question", {}).get("kind")
    return {
        "id": question.id, "failed": False,
        "grade_differences": {a: (g, judged[a]) for a, g in gold.items() if judged.get(a) != g},
        "missing_from_gold": {a: g for a, g in judged.items() if a not in gold and g > 0},
        "kind": (question.kind, kind), "kind_agrees": kind == question.kind,
        "sure": verdict.get("question", {}).get("sure"),
    }
