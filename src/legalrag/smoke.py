"""Smoke retrieval: embed hand-written questions, list the nearest chunks, mark the expected ones."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import psycopg
import yaml
from pydantic import BaseModel

from legalrag.embed import Embedder

NEAREST = (
    "SELECT a.source_code, a.kind, a.article_num, c.lang, c.chunk_index, "
    "(SELECT count(*) FROM chunks x WHERE x.article_uid = c.article_uid AND x.run_id = c.run_id), "
    "e.embedding <=> %s, c.header_text, c.body_text "
    "FROM chunk_embeddings e JOIN chunks c ON c.id = e.chunk_id "
    "JOIN articles a ON a.uid = c.article_uid "
    "WHERE e.model = 'BAAI/bge-m3' AND c.run_id = %s ORDER BY e.embedding <=> %s LIMIT %s"
)
LABELS = (
    "SELECT DISTINCT CASE WHEN source_code = 'code_travail' THEN article_num "
    "ELSE CASE kind WHEN 'article' THEN 'art ' ELSE 'rct ' END || article_num END FROM articles"
)


class Question(BaseModel):
    id: int
    group: str
    lang: str
    question: str
    expected: list[str] = []
    note: str = ""


@dataclass
class Hit:
    label: str
    lang: str
    chunk_index: int
    chunks: int
    distance: float
    header: str
    text: str


def load_questions(path: Path) -> list[Question]:
    questions = [Question(**q) for q in yaml.safe_load(path.read_text())]
    if len({q.id for q in questions}) != len(questions):
        raise ValueError("duplicate question id")
    return questions


def embed_questions(questions: list[Question], embedder: Embedder, batch_size: int = 16) -> np.ndarray:
    """One unit-length vector per question; bge-m3 takes queries without an instruction prefix."""
    vectors = np.asarray(embedder.encode([q.question for q in questions], batch_size), dtype=np.float32)
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def article_label(source_code: str, kind: str, article_num: str) -> str:
    if source_code == "code_travail":
        return article_num
    return f"{'art' if kind == 'article' else 'rct'} {article_num}"


def nearest(conn: psycopg.Connection, run_id: int, vector: np.ndarray, k: int = 5) -> list[Hit]:
    rows = conn.execute(NEAREST, (vector, run_id, vector, k)).fetchall()
    return [
        Hit(article_label(code, kind, num), lang, index, chunks, distance, header, text)
        for code, kind, num, lang, index, chunks, distance, header, text in rows
    ]


def known_labels(conn: psycopg.Connection) -> set[str]:
    return {r[0] for r in conn.execute(LABELS)}


def first_hit_rank(hits: list[Hit], expected: list[str]) -> int | None:
    """1-based rank of the first expected article among the hits, or None."""
    return next((i for i, h in enumerate(hits, 1) if h.label in expected), None)


def format_result(q: Question, hits: list[Hit], text_chars: int = 120) -> str:
    rank = first_hit_rank(hits, q.expected)
    if not q.expected:
        verdict = "no expected article"
    else:
        verdict = f"first expected article at rank {rank}" if rank else "expected article NOT in the top results"
    lines = [f"Q{q.id} [{q.group}, {q.lang}] {q.question}", f"  expected: {', '.join(q.expected) or '-'}  ({verdict})"]
    if q.note:
        lines.append(f"  note: {q.note}")
    for i, h in enumerate(hits, 1):
        mark = "*" if h.label in q.expected else " "
        where = f"{h.label} [{h.lang}] chunk {h.chunk_index + 1}/{h.chunks}"
        lines.append(f"  {i}{mark} {h.distance:.3f}  {where}")
        lines.append(f"       {h.header}")
        lines.append(f"       {h.text[:text_chars].replace(chr(10), ' ')}")
    return "\n".join(lines)
