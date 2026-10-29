"""Keyword search: BM25 over the lexemes Postgres already stores in chunks.tsv (stemmed text of the
chunk, french or english). The query goes through the same Postgres text-search configuration, so
both sides share one stemmer and stop-word list.
"""

import math
from collections import defaultdict

import psycopg

K1 = 1.2  # Robertson's usual defaults
B = 0.75
CONFIG = {"fr": "french", "en": "english"}
CHUNK_LEXEMES = (
    "SELECT c.id, a.source_code, a.kind, a.article_num, a.content_hash, l.lexeme, "
    "coalesce(array_length(l.positions, 1), 1) "
    "FROM chunks c JOIN articles a ON a.uid = c.article_uid, LATERAL unnest(c.tsv) l "
    "WHERE c.run_id = %s AND c.lang = %s"
)
QUERY_LEXEMES = "SELECT lexeme FROM unnest(to_tsvector(%s::regconfig, %s))"


class Bm25Index:
    """rows: (chunk id, source, kind, article number, content hash, lexeme, term frequency)."""

    def __init__(self, rows) -> None:
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self.length: dict[int, int] = defaultdict(int)
        self.article: dict[int, tuple[str, str, str, str]] = {}
        for chunk, source, kind, num, body_hash, lexeme, tf in rows:
            self.postings[lexeme].append((chunk, tf))
            self.length[chunk] += tf
            self.article[chunk] = (source, kind, num, body_hash)
        self.average = sum(self.length.values()) / max(len(self.length), 1)

    @classmethod
    def build(cls, conn: psycopg.Connection, run_id: int, lang: str) -> "Bm25Index":
        return cls(conn.execute(CHUNK_LEXEMES, (run_id, lang)).fetchall())

    def scores(self, lexemes: list[str]) -> dict[int, float]:
        """BM25 score of every chunk that holds at least one of the lexemes."""
        scores: dict[int, float] = defaultdict(float)
        total = len(self.length)
        for lexeme in lexemes:
            hits = self.postings.get(lexeme, [])
            idf = math.log(1 + (total - len(hits) + 0.5) / (len(hits) + 0.5))
            for chunk, tf in hits:
                norm = 1 - B + B * self.length[chunk] / self.average
                scores[chunk] += idf * tf * (K1 + 1) / (tf + K1 * norm)
        return scores

    def search(self, lexemes: list[str], top: int) -> list[tuple[str, str, str, str]]:
        """(source, kind, article number, content hash) of the best chunks, best first."""
        scores = self.scores(lexemes)
        best = sorted(scores, key=lambda chunk: (-scores[chunk], chunk))[:top]
        return [self.article[chunk] for chunk in best]


def query_lexemes(conn: psycopg.Connection, lang: str, text: str) -> list[str]:
    return [row[0] for row in conn.execute(QUERY_LEXEMES, (CONFIG[lang], text)).fetchall()]
