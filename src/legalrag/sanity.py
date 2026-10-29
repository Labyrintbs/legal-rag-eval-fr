"""Inspection check on the embeddings: do a few known questions find their article?"""

from dataclasses import dataclass

import numpy as np
import pyarrow.parquet as pq

from legalrag.embed import Embedder

TOP = 3
# (question, expected label): a Code du travail article number or a GDPR uid.
QUESTIONS = [
    ("préavis de démission", "L1237-1"),
    ("droit à l'effacement", "rgpd:fr:art_17"),
    ("durée légale du travail par semaine", "L3121-27"),
    ("notification d'une violation de données à l'autorité de contrôle", "rgpd:fr:art_33"),
    ("durée maximale de la période d'essai", "L1221-19"),
    ("quand le consentement est-il valable ?", "rgpd:fr:art_7"),
]


@dataclass
class Result:
    question: str
    expected: str
    hits: list[tuple[str, float]]  # (label, cosine) best first

    @property
    def ok(self) -> bool:
        return self.expected in [label for label, _ in self.hits]


def load(path) -> tuple[list[str], np.ndarray]:
    t = pq.read_table(path, columns=["article_uid", "vector"]).to_pydict()
    return t["article_uid"], np.array(t["vector"], dtype=np.float32)


def rank(
    labels: list[str],
    vectors: np.ndarray,
    embedder: Embedder,
    questions: list[tuple[str, str]] = QUESTIONS,
    top: int = TOP,
) -> list[Result]:
    """Rank every vector by cosine with each question; the stored vectors are already unit length."""
    q = np.asarray(embedder.encode_queries([text for text, _ in questions], len(questions)), np.float32)
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    sims = q @ vectors.T
    return [
        Result(text, expected, [(labels[j], float(sims[i, j])) for j in np.argsort(-sims[i])[:top]])
        for i, (text, expected) in enumerate(questions)
    ]
