"""Rebuild the database from nothing in a scratch database, compare it with the real one, drop it.

Raw files are re-checked, the vectors come from the GitHub Release, and every step is the public
command. The real database is only read.
"""

import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import psycopg

from legalrag.config import database_url

SCRATCH = "legalrag_rebuild"
TAG = "embeddings-bge-m3-main-v1"
VECTORS = "bge-m3-main.parquet"
LOCAL_VECTORS = Path("data/embeddings") / VECTORS

FINGERPRINT = {
    "rows per table": """
        SELECT concat_ws(' ', (SELECT count(*) FROM corpus_versions), (SELECT count(*) FROM articles),
            (SELECT count(*) FROM chunking_runs), (SELECT count(*) FROM chunks),
            (SELECT count(*) FROM chunk_embeddings))""",
    "articles": "SELECT md5(string_agg(uid || content_hash, ',' ORDER BY uid)) FROM articles",
    "chunks": """
        SELECT md5(string_agg(article_uid || ':' || chunk_index || ':' || embed_text_hash, ','
            ORDER BY article_uid, chunk_index)) FROM chunks""",
    "mean vector": "SELECT md5(avg(embedding)::text) FROM chunk_embeddings",
    "schema version": "SELECT version_num FROM alembic_version",
}


def with_database(url: str, name: str) -> str:
    return urlparse(url)._replace(path="/" + name).geturl()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*cmd: str, url: str) -> None:
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, env={**os.environ, "DATABASE_URL": url})


def fingerprint(url: str) -> dict[str, str]:
    with psycopg.connect(url) as conn:
        return {name: str(conn.execute(sql).fetchone()[0]) for name, sql in FINGERPRINT.items()}


def main() -> int:
    real = database_url()
    scratch = with_database(real, SCRATCH)
    admin = psycopg.connect(with_database(real, "postgres"), autocommit=True)
    admin.execute(f"CREATE DATABASE {SCRATCH}")  # fails when a leftover exists: look before deleting
    try:
        run("uv", "run", "legalrag", "migrate", url=scratch)
        run("uv", "run", "legalrag", "fetch", "all", url=scratch)
        with tempfile.TemporaryDirectory() as tmp:
            run("gh", "release", "download", TAG, "-p", VECTORS, "-D", tmp, url=scratch)
            if sha256(Path(tmp) / VECTORS) != sha256(LOCAL_VECTORS):
                print("FAIL  the Release vectors differ from data/embeddings")
                return 1
            run("uv", "run", "legalrag", "load-chunks", url=scratch)
            run("uv", "run", "legalrag", "load-embeddings", "--file", str(Path(tmp) / VECTORS), url=scratch)
        run("uv", "run", "legalrag", "db-check", url=scratch)
        old, new = fingerprint(real), fingerprint(scratch)
        for name in old:
            print(f"{'SAME' if old[name] == new[name] else 'DIFF'}  {name}: {old[name]} | {new[name]}")
        return 0 if old == new else 1
    except subprocess.CalledProcessError as e:
        print(f"FAIL  {' '.join(e.cmd)} exited with {e.returncode}")
        return 1
    finally:
        admin.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")
        admin.close()


if __name__ == "__main__":
    sys.exit(main())
