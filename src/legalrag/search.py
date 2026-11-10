"""Chunk-level search for the service (step 0d): the same exact dense search as the evaluation, but it returns
the best chunk of each of the top articles with its similarity, so that the chunk can be shown to the model
and cited. The evaluation (`evaluate.retrieve`) keeps returning articles only.
"""

from dataclasses import dataclass

import psycopg

from legalrag.dbcheck import _exact_scan
from legalrag.embed import MODEL
from legalrag.labels import article_label

TOP_ARTICLES = 5  # decision 7 of 0006
CHUNKS_SEARCHED = 400  # as in the evaluation: enough chunks to find 5 distinct articles
WEAK_THRESHOLD = 0.55  # decision 9 of 0006: below this top-1 similarity no answer is attempted (provisional)
HITS = (
    "SELECT c.chunk_index, c.header_text, c.body_text, a.source_code, a.kind, a.article_num, a.section_path, "
    "a.source_url, 1 - (e.embedding <=> %s) AS similarity "
    "FROM chunk_embeddings e JOIN chunks c ON c.id = e.chunk_id JOIN articles a ON a.uid = c.article_uid "
    "WHERE e.model = %s AND c.run_id = %s AND c.lang = %s ORDER BY e.embedding <=> %s LIMIT %s"
)


@dataclass(frozen=True)
class Hit:
    label: str
    chunk_index: int
    header: str
    text: str  # the body of the chunk: what is cited
    similarity: float
    section_path: str
    url: str


def best_chunk_per_article(rows: list[tuple], k: int = TOP_ARTICLES) -> list[Hit]:
    """The first (best) chunk of each distinct article, in order, until k articles."""
    hits, seen = [], set()
    for index, header, text, source, kind, num, path, url, similarity in rows:
        label = article_label(source, kind, num)
        if label in seen:
            continue
        seen.add(label)
        hits.append(Hit(label, index, header, text, float(similarity), path, url))
        if len(hits) == k:
            break
    return hits


def top_chunks(conn: psycopg.Connection, run_id: int, lang: str, vector, k: int = TOP_ARTICLES, model: str = MODEL) -> list[Hit]:
    with _exact_scan(conn):
        rows = conn.execute(HITS, (vector, model, run_id, lang, vector, CHUNKS_SEARCHED)).fetchall()
    return best_chunk_per_article(rows, k)


def is_weak(hits: list[Hit], threshold: float = WEAK_THRESHOLD) -> bool:
    """True when nothing was found or the best chunk is not close enough to the question."""
    return not hits or hits[0].similarity < threshold
