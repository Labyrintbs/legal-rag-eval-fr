"""Answer relevancy: does an answer respond to the question that was asked? (Not context relevancy, which asks whether the
retrieved passages are useful for the question.) Two ways were compared on a small subset before one was chosen (step 0f):
a judge with three labels, and the Ragas style (a model writes questions the answer would respond to; the score is the mean
cosine between them and the real question). The test of each way is a set of wrong pairs: an answer given with a question
that it does not answer must score lower than with its own question.
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, get_args

import numpy as np
from pydantic import BaseModel, Field, field_validator

Label = Literal["addresses", "partly", "does not address"]
LABELS = get_args(Label)
ORDER = {"does not address": 0, "partly": 1, "addresses": 2}
KINDS = ("matched", "random", "near")
MODEL = "deepseek-flash"


class Verdict(BaseModel):
    reason: str = ""
    label: Label

    @field_validator("label", mode="before")
    @classmethod
    def lowercase(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class Generated(BaseModel):
    questions: list[str] = Field(min_length=1)


@dataclass(frozen=True)
class Pair:
    key: str  # "<answer id>|<kind>"
    question: str
    answer: str
    kind: str  # matched: its own question; random: an unrelated one; near: the most similar question about other articles


def wrong_pairs(answer_id: str, answers: dict[str, str], questions: dict[str, str], vectors: dict[str, np.ndarray],
                gold: dict[str, set[str]], rng: random.Random) -> list[Pair]:
    """The answer with a random question and with the nearest question (cosine of the question vectors) whose gold
    articles are all different from those of its own question."""
    others = [q for q in questions if q != answer_id and not gold[q] & gold[answer_id]]
    near = max(others, key=lambda q: float(vectors[q] @ vectors[answer_id]))
    unrelated = rng.choice([q for q in others if q != near])
    return [Pair(f"{answer_id}|{kind}", questions[q], answers[answer_id], kind) for kind, q in (("random", unrelated), ("near", near))]


def make_pairs(answers: dict[str, str], questions: dict[str, str], vectors: dict[str, np.ndarray], gold: dict[str, set[str]],
               n: int | None, seed: int) -> list[Pair]:
    """For n answers drawn at random (all of them when n is None): the answer with its own question, then its wrong
    pairs. `answers`: id -> the answer's claims."""
    rng = random.Random(seed)
    chosen = sorted(answers) if n is None else rng.sample(sorted(answers), n)
    pairs = []
    for a in chosen:
        pairs += [Pair(f"{a}|matched", questions[a], answers[a], "matched"), *wrong_pairs(a, answers, questions, vectors, gold, rng)]
    return pairs


def ragas_score(question_vector: np.ndarray, generated_vectors: np.ndarray) -> float:
    """Mean cosine similarity between the real question and the questions written from the answer (unit vectors)."""
    return float(np.mean(generated_vectors @ question_vector))


def separation(matched: Sequence[float], wrong: Sequence[float]) -> float:
    """Share of (matched, wrong) score pairs in which the matched pair scores higher; a tie counts half. 1.0 means
    the measure always tells the answer's own question from another one; 0.5 is chance."""
    pairs = [(m, w) for m in matched for w in wrong]
    return sum(1.0 if m > w else 0.5 if m == w else 0.0 for m, w in pairs) / len(pairs)

