"""Load articles, chunks and vectors into Postgres; every loader can be re-run safely."""

from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import psycopg
import pyarrow.parquet as pq
from psycopg.types.json import Jsonb

from legalrag.embed import DIM, MODEL, embed_text_hash
from legalrag.fetch import sha256_of
from legalrag.models import Article, Chunk

HNSW_INDEX = "chunk_embeddings_hnsw_bge_m3"
_GDPR_URL = "https://eur-lex.europa.eu/legal-content/{lang}/TXT/?uri=CELEX:32016R0679"

# (source_code, lang) -> corpus_versions fields; the raw file name locates the file to checksum.
CORPORA = {
    ("code_travail", "fr"): {
        "source_key": "legi_vincegx33",
        "source_name": "VinceGx33/legi-french-law-2025, Code du travail rows (DILA LEGI dump)",
        "source_url": "https://huggingface.co/datasets/VinceGx33/legi-french-law-2025",
        "snapshot_date": date(2025, 7, 13),
        "file": "legi_vincegx33_train.parquet",
        "license": "Etalab-2.0 / Licence Ouverte 2.0",
        "notes": "Articles in force only, filtered on texte_titre = code du travail.",
    },
    ("rgpd", "fr"): {
        "source_key": "gdpr_fr",
        "source_name": "Regulation (EU) 2016/679, French, EU Publications Office",
        "source_url": _GDPR_URL.format(lang="FR"),
        "snapshot_date": date(2016, 5, 4),
        "file": "gdpr_fr.xhtml",
        "license": "CC BY 4.0",
        "notes": "Text as published in OJ L 119; later corrigenda not verified.",
    },
    ("rgpd", "en"): {
        "source_key": "gdpr_en",
        "source_name": "Regulation (EU) 2016/679, English, EU Publications Office",
        "source_url": _GDPR_URL.format(lang="EN"),
        "snapshot_date": date(2016, 5, 4),
        "file": "gdpr_en.xhtml",
        "license": "CC BY 4.0",
        "notes": "Text as published in OJ L 119; later corrigenda not verified.",
    },
}


def register_corpus(
    conn: psycopg.Connection, source_code: str, lang: str, raw_dir: Path, row_count: int
) -> int:
    meta = CORPORA[(source_code, lang)]
    path = raw_dir / meta["file"]
    retrieved = datetime.fromtimestamp(path.stat().st_mtime, UTC)  # file time, not load time
    row = conn.execute(
        """
        INSERT INTO corpus_versions (source_key, source_name, source_url, snapshot_date,
            retrieved_at, file_sha256, row_count, license, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (source_key, file_sha256) DO UPDATE SET row_count = EXCLUDED.row_count
        RETURNING id
        """,
        (meta["source_key"], meta["source_name"], meta["source_url"], meta["snapshot_date"],
         retrieved, sha256_of(path), row_count, meta["license"], meta["notes"]),
    ).fetchone()
    return row[0]


def load_articles(conn: psycopg.Connection, articles: list[Article], corpus_id: int) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO articles (uid, corpus_version_id, source_code, lang, kind, native_id,
                article_num, title, section_path, body_text, valid_from, valid_to, status,
                content_hash, source_url, extra)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (uid) DO UPDATE SET
                corpus_version_id = EXCLUDED.corpus_version_id, kind = EXCLUDED.kind,
                article_num = EXCLUDED.article_num, title = EXCLUDED.title,
                section_path = EXCLUDED.section_path, body_text = EXCLUDED.body_text,
                valid_from = EXCLUDED.valid_from, valid_to = EXCLUDED.valid_to,
                status = EXCLUDED.status, content_hash = EXCLUDED.content_hash,
                source_url = EXCLUDED.source_url, extra = EXCLUDED.extra
            """,
            [
                (a.uid, corpus_id, a.source_code, a.lang, a.kind, a.native_id, a.article_num,
                 a.title, a.section_path, a.body_text, a.valid_from, a.valid_to, a.status,
                 a.content_hash, a.source_url, Jsonb(a.extra))
                for a in articles
            ],
        )


def get_or_create_run(
    conn: psycopg.Connection, name: str, settings: dict, tokenizer: str, split_rule: str,
    code_version: str,
) -> int:
    """Return the run id; refuse a run that exists with other settings."""
    row = conn.execute(
        "SELECT id, header_style, header_k, max_tokens, params FROM chunking_runs WHERE name = %s",
        (name,),
    ).fetchone()
    if row:
        same = (row[1], row[2], row[3], row[4]) == (
            settings["style"], settings["k"], settings["max_tokens"], settings
        )
        if not same:
            raise ValueError(f"chunking run {name!r} exists with other settings; use a new name")
        return row[0]
    return conn.execute(
        """
        INSERT INTO chunking_runs (name, header_style, header_k, max_tokens, split_rule,
            tokenizer, code_version, params)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
        """,
        (name, settings["style"], settings["k"], settings["max_tokens"], split_rule, tokenizer,
         code_version, Jsonb(settings)),
    ).fetchone()[0]


def load_chunks(conn: psycopg.Connection, run_id: int, chunks: list[Chunk]) -> int:
    """Insert the chunks missing from the run; return how many were inserted.

    A run is immutable: if a stored chunk differs from the incoming one, or the run holds a chunk
    that is not incoming, the chunking changed and a new run name is needed.
    """
    incoming = {(c.article_uid, c.chunk_index): embed_text_hash(c.embed_text) for c in chunks}
    stored = {
        (uid, idx): h
        for uid, idx, h in conn.execute(
            "SELECT article_uid, chunk_index, embed_text_hash FROM chunks WHERE run_id = %s",
            (run_id,),
        )
    }
    changed = [k for k, h in stored.items() if incoming.get(k) != h]
    if changed:
        raise ValueError(f"run holds {len(changed)} chunks that differ from the new ones, e.g. {changed[0]}")
    todo = [c for c in chunks if (c.article_uid, c.chunk_index) not in stored]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO chunks (run_id, article_uid, chunk_index, lang, header_text, body_text,
                embed_text, embed_text_hash, token_count, extra)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (run_id, c.article_uid, c.chunk_index, c.lang, c.header_text, c.body_text,
                 c.embed_text, embed_text_hash(c.embed_text), c.token_count, Jsonb(c.extra))
                for c in todo
            ],
        )
    return len(todo)


def load_embeddings(conn: psycopg.Connection, run_id: int, path: Path) -> int:
    """Load a vectors file produced by `legalrag embed`, matching chunks by key and text hash."""
    table = pq.read_table(path)
    uids = table.column("article_uid").to_pylist()
    indexes = table.column("chunk_index").to_pylist()
    hashes = table.column("embed_text_hash").to_pylist()
    models = set(table.column("model").to_pylist())
    revisions = set(table.column("model_revision").to_pylist())
    if len(models) != 1 or len(revisions) != 1 or set(table.column("dim").to_pylist()) != {DIM}:
        raise ValueError("the file must hold one model, one revision and dimension 1024")
    vectors = table.column("vector").combine_chunks().values.to_numpy().reshape(-1, DIM)

    ids = {
        (uid, idx): (cid, h)
        for cid, uid, idx, h in conn.execute(
            "SELECT id, article_uid, chunk_index, embed_text_hash FROM chunks WHERE run_id = %s",
            (run_id,),
        )
    }
    keys = list(zip(uids, indexes, strict=True))
    if set(keys) != set(ids):
        raise ValueError(f"file has {len(set(keys))} keys, the run has {len(ids)}; sets differ")
    bad = [k for k, h in zip(keys, hashes, strict=True) if ids[k][1] != h]
    if bad:
        raise ValueError(f"{len(bad)} vectors were made from other text than the stored chunks, e.g. {bad[0]}")

    model, revision = models.pop(), revisions.pop()
    with conn.transaction(), conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO chunk_embeddings (chunk_id, model, model_revision, dim, embedding,
                embed_text_hash)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (chunk_id, model) DO UPDATE SET model_revision = EXCLUDED.model_revision,
                embedding = EXCLUDED.embedding, embed_text_hash = EXCLUDED.embed_text_hash,
                created_at = now()
            """,
            [
                (ids[k][0], model, revision, DIM, np.asarray(vectors[i], dtype=np.float32), hashes[i])
                for i, k in enumerate(keys)
            ],
        )
    return len(keys)


def run_size(conn: psycopg.Connection, name: str) -> tuple[int, int] | None:
    """(chunks, vectors) of the named run, or None when there is no such run."""
    row = conn.execute(
        """
        SELECT r.id, count(DISTINCT c.id), count(e.chunk_id)
        FROM chunking_runs r
        LEFT JOIN chunks c ON c.run_id = r.id
        LEFT JOIN chunk_embeddings e ON e.chunk_id = c.id
        WHERE r.name = %s
        GROUP BY r.id
        """,
        (name,),
    ).fetchone()
    return None if row is None else (row[1], row[2])


def delete_run(conn: psycopg.Connection, name: str) -> None:
    """Delete the run; its chunks and their vectors go with it (ON DELETE CASCADE). Articles stay."""
    conn.execute("DELETE FROM chunking_runs WHERE name = %s", (name,))


def build_hnsw_index(conn: psycopg.Connection) -> None:
    """Partial HNSW index for the one model; queries must repeat `model = '<model>'`."""
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS {HNSW_INDEX} ON chunk_embeddings "
        f"USING hnsw (embedding vector_cosine_ops) WHERE model = '{MODEL}'"
    )
