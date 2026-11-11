"""A small frozen copy of the database for the quality gate in CI (step 0e).

It holds, for every dev question, the 20 articles the full search ranks first (all their chunks and vectors)
and the gold articles, plus the question vectors. The CI machine has no model and no GPU: it loads the copy
into a throwaway database and runs the real search and metric code. Because the top 20 of every question
are all in the copy, the exact search ranks them as in the full database, so the metrics match the full
evaluation on those questions. A change of embedding model or chunking is not seen by the gate.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import psycopg
from psycopg.types.json import Jsonb

from legalrag.corpus.labels import article_label
from legalrag.evaluation import gold
from legalrag.index.dbcheck import _exact_scan
from legalrag.index.embed import MODEL

DEPTH = 20  # as the deepest cut-off of the evaluation (Recall@20)
CHUNKS_SEARCHED = 400
RUN = "default"
ARTICLE_COLUMNS = ("uid", "source_code", "lang", "kind", "native_id", "article_num", "title", "section_path", "body_text",
                   "valid_from", "valid_to", "status", "content_hash", "source_url", "extra")
CHUNK_COLUMNS = ("article_uid", "chunk_index", "lang", "header_text", "body_text", "embed_text", "embed_text_hash", "token_count", "extra")
NEAREST = (
    "SELECT c.article_uid FROM chunk_embeddings e JOIN chunks c ON c.id = e.chunk_id "
    "WHERE e.model = %s AND c.run_id = %s AND c.lang = %s ORDER BY e.embedding <=> %s LIMIT %s"
)


@dataclass(frozen=True)
class Fixture:
    articles: list[dict]
    chunks: list[dict]
    vectors: np.ndarray  # one row per chunk, same order
    questions: dict[str, str]  # id -> text, as in eval/gold.jsonl when the fixture was made
    question_vectors: np.ndarray  # one row per question, same order


def top_articles(conn: psycopg.Connection, run_id: int, lang: str, vector, depth: int = DEPTH) -> list[str]:
    """Uids of the first `depth` distinct articles of the exact dense search, best first."""
    with _exact_scan(conn):
        rows = conn.execute(NEAREST, (MODEL, run_id, lang, vector, CHUNKS_SEARCHED)).fetchall()
    return list(dict.fromkeys(uid for (uid,) in rows))[:depth]


def gold_uids(conn: psycopg.Connection, questions: list[gold.GoldQuestion]) -> set[str]:
    wanted = {(g.source, g.lang, g.article) for q in questions for g in q.gold}
    rows = conn.execute("SELECT uid, source_code, kind, article_num, lang FROM articles").fetchall()
    return {uid for uid, source, kind, num, lang in rows if (source, lang, article_label(source, kind, num)) in wanted}


def collect(conn: psycopg.Connection, run_id: int, questions: list[gold.GoldQuestion], question_vectors, depth: int = DEPTH) -> Fixture:
    uids = gold_uids(conn, questions)
    for q, vector in zip(questions, question_vectors, strict=True):
        uids.update(top_articles(conn, run_id, q.lang, vector, depth))
    ordered = sorted(uids)
    articles = [dict(zip(ARTICLE_COLUMNS, row, strict=True)) for row in conn.execute(
        f"SELECT {', '.join(ARTICLE_COLUMNS)} FROM articles WHERE uid = ANY(%s) ORDER BY uid", (ordered,))]
    rows = conn.execute(
        f"SELECT {', '.join('c.' + c for c in CHUNK_COLUMNS)}, e.embedding FROM chunks c "
        "JOIN chunk_embeddings e ON e.chunk_id = c.id AND e.model = %s "
        "WHERE c.run_id = %s AND c.article_uid = ANY(%s) ORDER BY c.article_uid, c.chunk_index", (MODEL, run_id, ordered)).fetchall()
    chunks = [dict(zip(CHUNK_COLUMNS, row[:-1], strict=True)) for row in rows]
    vectors = np.stack([row[-1].to_numpy().astype(np.float32) for row in rows])
    return Fixture(articles, chunks, vectors, {q.id: q.question for q in questions}, np.asarray(question_vectors, dtype=np.float32))


def save(fixture: Fixture, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, rows in (("articles", fixture.articles), ("chunks", fixture.chunks)):
        (directory / f"{name}.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in rows) + "\n")
    (directory / "questions.json").write_text(json.dumps(fixture.questions, ensure_ascii=False, indent=0))
    np.save(directory / "vectors.npy", fixture.vectors)
    np.save(directory / "question_vectors.npy", fixture.question_vectors)


def read(directory: Path) -> Fixture:
    def lines(name: str) -> list[dict]:
        return [json.loads(line) for line in (directory / f"{name}.jsonl").read_text().splitlines()]

    return Fixture(lines("articles"), lines("chunks"), np.load(directory / "vectors.npy"),
                   json.loads((directory / "questions.json").read_text()), np.load(directory / "question_vectors.npy"))


def load(conn: psycopg.Connection, fixture: Fixture) -> int:
    """Insert the copy into an empty, migrated database; return the run id."""
    corpus_id = conn.execute(
        "INSERT INTO corpus_versions (source_key, source_name, source_url, retrieved_at, file_sha256, row_count, license) "
        "VALUES ('ci_fixture', 'quality-gate fixture', 'n/a', now(), 'n/a', %s, 'see NOTICE.md') RETURNING id",
        (len(fixture.articles),)).fetchone()[0]
    run_id = conn.execute(
        "INSERT INTO chunking_runs (name, header_style, max_tokens, split_rule, tokenizer, code_version, params) "
        "VALUES (%s, 'fixture', 0, 'fixture', 'fixture', 'fixture', '{}') RETURNING id", (RUN,)).fetchone()[0]
    with conn.cursor() as cur:
        columns = [c for c in ARTICLE_COLUMNS if c != "extra"]
        cur.executemany(
            f"INSERT INTO articles ({', '.join(columns)}, corpus_version_id, extra) VALUES ({', '.join(['%s'] * len(columns))}, %s, %s)",
            [[a[c] for c in columns] + [corpus_id, Jsonb(a["extra"])] for a in fixture.articles])
        for chunk, vector in zip(fixture.chunks, fixture.vectors, strict=True):
            chunk_id = cur.execute(
                f"INSERT INTO chunks (run_id, {', '.join(CHUNK_COLUMNS)}) VALUES (%s, {', '.join(['%s'] * len(CHUNK_COLUMNS))}) RETURNING id",
                [run_id] + [Jsonb(chunk[c]) if c == "extra" else chunk[c] for c in CHUNK_COLUMNS]).fetchone()[0]
            cur.execute("INSERT INTO chunk_embeddings (chunk_id, model, model_revision, dim, embedding, embed_text_hash) "
                        "VALUES (%s, %s, 'fixture', %s, %s, %s)", (chunk_id, MODEL, vector.shape[0], vector, chunk["embed_text_hash"]))
    return run_id
