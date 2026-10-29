"""Reranker: a cross-encoder reads the question and one chunk together and gives a relevance score.
The candidates of the first search (dense) are re-ordered by it; an article scores as its best chunk.
"""

from typing import Protocol

import psycopg

from legalrag.smoke import article_label, split_label

DEFAULT_MODEL = "BAAI/bge-reranker-v2-m3"
MAX_LENGTH = 1024  # tokens of question and chunk together
BATCH_SIZE = 16
CANDIDATE_TEXTS = (
    "SELECT a.source_code, a.kind, a.article_num, c.embed_text FROM chunks c "
    "JOIN articles a ON a.uid = c.article_uid WHERE c.run_id = %s AND c.lang = %s "
    "AND a.source_code || '|' || a.kind || '|' || a.article_num = ANY(%s)"
)


class Scorer(Protocol):
    def score(self, pairs: list[tuple[str, str]]) -> list[float]: ...


class CrossEncoderScorer:
    """A sentence-transformers cross-encoder. Imports torch lazily."""

    def __init__(self, model: str = DEFAULT_MODEL, device: str = "auto") -> None:
        import torch
        from huggingface_hub import model_info
        from sentence_transformers import CrossEncoder

        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model_name, self.device = model, device
        self.revision = model_info(model).sha
        self.model = CrossEncoder(model, device=device, max_length=MAX_LENGTH, revision=self.revision)

    def score(self, pairs: list[tuple[str, str]]) -> list[float]:
        return [float(s) for s in self.model.predict(pairs, batch_size=BATCH_SIZE, show_progress_bar=False)]

    def info(self) -> dict:
        return {"model": self.model_name, "model_revision": self.revision, "device": self.device,
                "max_length": MAX_LENGTH}


def chunk_texts(conn: psycopg.Connection, run_id: int, lang: str, labels: list[str]) -> dict[str, list[str]]:
    """Embedded text of every chunk of the given articles, by article label."""
    keys = ["|".join(split_label(label)) for label in labels]
    texts: dict[str, list[str]] = {}
    for source, kind, num, text in conn.execute(CANDIDATE_TEXTS, (run_id, lang, keys)).fetchall():
        texts.setdefault(article_label(source, kind, num), []).append(text)
    return texts


def rerank(
    conn: psycopg.Connection, run_id: int, lang: str, question: str, candidates: list[tuple[str, str]],
    scorer: Scorer, keep: int,
) -> list[tuple[str, str]]:
    """The candidates ordered by the best chunk score of each article; equal scores keep the first
    search's order."""
    texts = chunk_texts(conn, run_id, lang, [label for label, _ in candidates])
    pairs = [(question, text) for label, _ in candidates for text in texts.get(label, [])]
    scores = iter(scorer.score(pairs))
    best = {}
    for label, _ in candidates:
        best[label] = max((next(scores) for _ in texts.get(label, [])), default=float("-inf"))
    ordered = sorted(candidates, key=lambda candidate: -best[candidate[0]])
    return ordered[:keep]
