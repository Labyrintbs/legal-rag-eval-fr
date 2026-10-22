"""Checks on what is stored in Postgres after loading."""

import psycopg

from legalrag.embed import DIM, MODEL
from legalrag.store import HNSW_INDEX
from legalrag.verify import Check

NEIGHBOUR_QUERY = (
    "SELECT c.article_uid, c.chunk_index FROM chunk_embeddings e JOIN chunks c ON c.id = e.chunk_id "
    "WHERE e.model = 'BAAI/bge-m3' AND c.run_id = %s {extra} "
    "ORDER BY e.embedding <=> %s LIMIT %s"
)


def _one(conn: psycopg.Connection, sql: str, *params):
    return conn.execute(sql, params).fetchone()[0]


def _unit(uid: str) -> str:
    """'rgpd:fr:art_5' -> 'art_5': the same unit in French and English."""
    return uid.rsplit(":", 1)[1]


def cross_language_rate(conn: psycopg.Connection, run_id: int) -> tuple[int, int]:
    """For each French GDPR chunk, is its nearest English chunk the same article or recital?"""
    rows = conn.execute(
        "SELECT c.article_uid, e.embedding FROM chunks c JOIN chunk_embeddings e ON e.chunk_id = c.id "
        "WHERE c.run_id = %s AND c.article_uid LIKE 'rgpd:fr:%%' AND e.model = %s",
        (run_id, MODEL),
    ).fetchall()
    hits = 0
    for uid, vec in rows:
        sql = NEIGHBOUR_QUERY.format(extra="AND c.lang = 'en'")
        nearest = conn.execute(sql, (run_id, vec, 1)).fetchone()
        hits += nearest is not None and _unit(nearest[0]) == _unit(uid)
    return hits, len(rows)


def db_checks(conn: psycopg.Connection, run_name: str, expected_chunks: int) -> list[Check]:
    run_id = _one(conn, "SELECT id FROM chunking_runs WHERE name = %s", run_name)
    chunks = _one(conn, "SELECT count(*) FROM chunks WHERE run_id = %s", run_id)
    vectors = _one(
        conn,
        "SELECT count(*) FROM chunk_embeddings e JOIN chunks c ON c.id = e.chunk_id "
        "WHERE c.run_id = %s AND e.model = %s",
        run_id, MODEL,
    )
    without = _one(
        conn,
        "SELECT count(*) FROM chunks c WHERE c.run_id = %s AND NOT EXISTS "
        "(SELECT 1 FROM chunk_embeddings e WHERE e.chunk_id = c.id AND e.model = %s)",
        run_id, MODEL,
    )
    bad_dim = _one(conn, "SELECT count(*) FROM chunk_embeddings WHERE vector_dims(embedding) <> %s", DIM)
    off_norm = _one(
        conn, "SELECT count(*) FROM chunk_embeddings WHERE abs(vector_norm(embedding) - 1) > 0.001"
    )
    hash_diff = _one(
        conn,
        "SELECT count(*) FROM chunk_embeddings e JOIN chunks c ON c.id = e.chunk_id "
        "WHERE e.embed_text_hash <> c.embed_text_hash",
    )
    empty_tsv = _one(conn, "SELECT count(*) FROM chunks WHERE run_id = %s AND tsv = ''::tsvector", run_id)
    orphans = _one(
        conn, "SELECT count(*) FROM chunks c WHERE NOT EXISTS (SELECT 1 FROM articles a WHERE a.uid = c.article_uid)"
    )
    index = _one(conn, "SELECT count(*) FROM pg_indexes WHERE indexname = %s", HNSW_INDEX)

    probe = conn.execute(
        "SELECT e.embedding FROM chunk_embeddings e JOIN chunks c ON c.id = e.chunk_id "
        "WHERE c.run_id = %s AND e.model = %s ORDER BY c.id LIMIT 1", (run_id, MODEL),
    ).fetchone()[0]
    plan = "\n".join(
        r[0] for r in conn.execute(
            "EXPLAIN " + NEIGHBOUR_QUERY.format(extra=""), (run_id, probe, 5)
        )
    )
    hits, total = cross_language_rate(conn, run_id)
    rate = hits / total if total else 0.0
    return [
        (f"{expected_chunks} chunks in run {run_name}", chunks == expected_chunks, f"got {chunks}"),
        ("every chunk has a vector for the model", vectors == chunks and without == 0, f"{vectors} vectors, {without} chunks without"),
        (f"every vector has {DIM} dimensions", bad_dim == 0, f"{bad_dim} wrong"),
        ("every vector has unit length (+/- 0.001)", off_norm == 0, f"{off_norm} off"),
        ("vector text hash equals chunk text hash", hash_diff == 0, f"{hash_diff} differ"),
        ("every chunk has a keyword-search vector", empty_tsv == 0, f"{empty_tsv} empty"),
        ("every chunk belongs to a stored article", orphans == 0, f"{orphans} orphans"),
        (f"HNSW index {HNSW_INDEX} exists", index == 1, ""),
        ("planner uses the HNSW index for a nearest-neighbour query", HNSW_INDEX in plan, plan.splitlines()[0] if plan else ""),
        ("French GDPR chunk -> same unit in English (top 1) >= 95%", rate >= 0.95, f"{hits}/{total} = {rate:.1%}"),
    ]
