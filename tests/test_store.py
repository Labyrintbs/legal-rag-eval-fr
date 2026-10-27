import json
import uuid
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import psycopg
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from legalrag import db, smoke, store
from legalrag.config import database_url
from legalrag.dbcheck import NEIGHBOUR_QUERY, _exact_scan, cross_language_rate, index_recall
from legalrag.embed import DIM, MODEL, embed_text_hash
from legalrag.ingest import build_chunks
from legalrag.sources import gdpr, legi

FIXTURES = Path(__file__).parent / "fixtures"
SETTINGS = {"style": "last_k", "k": 3, "max_tokens": 100_000, "collapse_repeats": False}


def with_database(url: str, name: str) -> str:
    return urlparse(url)._replace(path="/" + name).geturl()


def words(s: str) -> int:
    return len(s.split())


@pytest.fixture(scope="module")
def database_name():
    """A throwaway database on the dev server; the tests skip when no server is reachable."""
    try:
        admin = psycopg.connect(with_database(database_url(), "postgres"), autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("no Postgres reachable at DATABASE_URL (run `make db-up`)")
    name = f"legalrag_test_{uuid.uuid4().hex[:8]}"
    admin.execute(f"CREATE DATABASE {name}")
    try:
        db.migrate(with_database(database_url(), name))
        yield name
    finally:  # also when the migration fails, so no throwaway database is left behind
        admin.execute(f"DROP DATABASE {name} WITH (FORCE)")
        admin.close()


@pytest.fixture
def conn(database_name):
    c = db.connect(with_database(database_url(), database_name))
    yield c
    c.rollback()  # each test leaves the database as it found it
    c.close()


@pytest.fixture(scope="module")
def corpora():
    legi_articles = legi.to_articles(pd.DataFrame(json.loads((FIXTURES / "code_travail_sample.json").read_text())))
    fr = gdpr.parse(FIXTURES / "gdpr_fr_excerpt.xhtml", "fr")
    en = [a.model_copy(update={"uid": a.uid.replace("rgpd:fr:", "rgpd:en:"), "lang": "en"}) for a in fr]
    return {("code_travail", "fr"): legi_articles, ("rgpd", "fr"): fr, ("rgpd", "en"): en}


@pytest.fixture
def raw_dir(tmp_path):
    """Dummy raw files: register_corpus only needs something to checksum."""
    for meta in store.CORPORA.values():
        (tmp_path / meta["file"]).write_bytes(meta["file"].encode())
    return tmp_path


@pytest.fixture
def loaded(conn, corpora, raw_dir):
    """Articles and chunks of the fixtures loaded under one run; returns (run_id, chunks)."""
    for (code, lang), articles in corpora.items():
        store.load_articles(conn, articles, store.register_corpus(conn, code, lang, raw_dir, len(articles)))
    run_id = store.get_or_create_run(conn, "t", SETTINGS, "BAAI/bge-m3", "rule", "abc")
    chunks = [c for arts in corpora.values() for c in build_chunks(arts, words, **SETTINGS)]
    store.load_chunks(conn, run_id, chunks)
    return run_id, chunks


def count(conn, table):
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def unit_vectors(chunks, same_unit_same_vector=True):
    rng = np.random.default_rng(0)
    seen: dict[str, np.ndarray] = {}
    out = []
    for c in chunks:
        key = c.article_uid.rsplit(":", 1)[1] + str(c.chunk_index) if same_unit_same_vector else c.article_uid
        if key not in seen:
            v = rng.normal(size=DIM).astype(np.float32)
            seen[key] = v / np.linalg.norm(v)
        out.append(seen[key])
    return np.array(out)


def write_vectors(path, chunks, vectors, hashes=None):
    n = len(chunks)
    pq.write_table(
        pa.table(
            {
                "article_uid": [c.article_uid for c in chunks],
                "chunk_index": pa.array([c.chunk_index for c in chunks], pa.int32()),
                "lang": [c.lang for c in chunks],
                "model": [MODEL] * n,
                "model_revision": ["rev"] * n,
                "dim": pa.array([DIM] * n, pa.int32()),
                "embed_text_hash": hashes or [embed_text_hash(c.embed_text) for c in chunks],
                "vector": pa.FixedSizeListArray.from_arrays(pa.array(vectors.ravel()), DIM),
            }
        ),
        path,
    )


def test_corpus_articles_and_chunks_are_stored(conn, loaded, corpora):
    assert count(conn, "corpus_versions") == 3
    assert count(conn, "articles") == sum(len(a) for a in corpora.values())
    assert count(conn, "chunks") == len(loaded[1])
    row = conn.execute("SELECT valid_from, status, kind FROM articles WHERE article_num = 'L1237-1'").fetchone()
    assert row == (date(2008, 5, 1), "VIGUEUR", "article")


def test_keyword_column_uses_the_dictionary_of_the_chunk_language(conn, loaded):
    fr = conn.execute(
        "SELECT article_uid FROM chunks WHERE lang = 'fr' AND tsv @@ plainto_tsquery('french', 'démission')"
    ).fetchall()
    assert ("code_travail:fr:LEGIARTI000006901174",) in fr
    # The English fixture chunks hold French text, so the two dictionaries give different results.
    wrong = conn.execute(
        "SELECT count(*) FROM chunks WHERE (lang = 'fr' AND tsv <> to_tsvector('french', embed_text)) "
        "OR (lang = 'en' AND tsv <> to_tsvector('english', embed_text))"
    ).fetchone()[0]
    differs = conn.execute(
        "SELECT count(*) FROM chunks WHERE lang = 'en' AND tsv <> to_tsvector('french', embed_text)"
    ).fetchone()[0]
    assert wrong == 0 and differs > 0


def test_loading_twice_adds_nothing(conn, loaded, corpora, raw_dir):
    run_id, chunks = loaded
    assert store.load_chunks(conn, run_id, chunks) == 0
    for (code, lang), articles in corpora.items():
        store.load_articles(conn, articles, store.register_corpus(conn, code, lang, raw_dir, len(articles)))
    assert count(conn, "chunks") == len(chunks)
    assert count(conn, "articles") == sum(len(a) for a in corpora.values())
    assert count(conn, "corpus_versions") == 3


def test_a_run_refuses_other_settings_and_changed_chunks(conn, loaded):
    run_id, chunks = loaded
    with pytest.raises(ValueError, match="other settings"):
        store.get_or_create_run(conn, "t", {**SETTINGS, "k": 2}, "BAAI/bge-m3", "rule", "abc")
    changed = [chunks[0].model_copy(update={"embed_text": chunks[0].embed_text + " x"}), *chunks[1:]]
    with pytest.raises(ValueError, match="differ"):
        store.load_chunks(conn, run_id, changed)


def test_vectors_load_by_key_and_hash(conn, loaded, tmp_path):
    run_id, chunks = loaded
    path = tmp_path / "v.parquet"
    write_vectors(path, chunks, unit_vectors(chunks))
    assert store.load_embeddings(conn, run_id, path) == len(chunks)
    assert store.load_embeddings(conn, run_id, path) == len(chunks)  # re-run replaces in place
    assert count(conn, "chunk_embeddings") == len(chunks)


def test_vectors_made_from_other_text_are_refused_and_nothing_is_stored(conn, loaded, tmp_path):
    run_id, chunks = loaded
    hashes = [embed_text_hash(c.embed_text) for c in chunks]
    hashes[3] = "0" * 64
    path = tmp_path / "v.parquet"
    write_vectors(path, chunks, unit_vectors(chunks), hashes)
    with pytest.raises(ValueError, match="other text"):
        store.load_embeddings(conn, run_id, path)
    assert count(conn, "chunk_embeddings") == 0


def test_vectors_for_a_different_chunk_set_are_refused(conn, loaded, tmp_path):
    run_id, chunks = loaded
    path = tmp_path / "v.parquet"
    write_vectors(path, chunks[1:], unit_vectors(chunks[1:]))
    with pytest.raises(ValueError, match="sets differ"):
        store.load_embeddings(conn, run_id, path)


def test_hnsw_index_serves_cosine_queries_for_the_model(conn, loaded, tmp_path):
    run_id, chunks = loaded
    path = tmp_path / "v.parquet"
    vectors = unit_vectors(chunks, same_unit_same_vector=False)
    write_vectors(path, chunks, vectors)
    store.load_embeddings(conn, run_id, path)
    store.build_hnsw_index(conn)
    store.build_hnsw_index(conn)  # idempotent
    query = "SELECT chunk_id FROM chunk_embeddings WHERE model = 'BAAI/bge-m3' ORDER BY embedding <=> %s LIMIT 1"
    conn.execute("SET LOCAL enable_seqscan = off")  # a table this small would otherwise be scanned
    plan = " ".join(r[0] for r in conn.execute("EXPLAIN " + query, (vectors[5],)))
    assert store.HNSW_INDEX in plan
    nearest = conn.execute(query, (vectors[5],)).fetchone()[0]
    assert conn.execute("SELECT article_uid, chunk_index FROM chunks WHERE id = %s", (nearest,)).fetchone() == (
        chunks[5].article_uid, chunks[5].chunk_index)


def test_cross_language_rate_counts_matching_units(conn, loaded, tmp_path):
    run_id, chunks = loaded
    vectors = unit_vectors(chunks)  # a French and an English chunk of one unit share a vector
    path = tmp_path / "v.parquet"
    write_vectors(path, chunks, vectors)
    store.load_embeddings(conn, run_id, path)
    hits, total = cross_language_rate(conn, run_id)
    assert total == sum(c.article_uid.startswith("rgpd:fr:") for c in chunks) > 0
    assert hits == total


def test_unknown_lang_and_kind_are_refused(conn, loaded):
    for column, value, table in (("lang", "FR", "articles"), ("kind", "preamble", "articles"), ("lang", "de", "chunks")):
        with pytest.raises(psycopg.errors.CheckViolation), conn.transaction():
            conn.execute(f"UPDATE {table} SET {column} = %s", (value,))


def test_deleting_a_run_removes_its_chunks_and_vectors_but_not_articles(conn, loaded, tmp_path):
    run_id, chunks = loaded
    write_vectors(tmp_path / "v.parquet", chunks, unit_vectors(chunks))
    store.load_embeddings(conn, run_id, tmp_path / "v.parquet")
    articles = count(conn, "articles")
    assert store.run_size(conn, "t") == (len(chunks), len(chunks))
    store.delete_run(conn, "t")
    assert store.run_size(conn, "t") is None
    assert (count(conn, "chunking_runs"), count(conn, "chunks"), count(conn, "chunk_embeddings")) == (0, 0, 0)
    assert count(conn, "articles") == articles


def test_smoke_finds_the_chunk_a_question_vector_equals_and_knows_the_labels(conn, loaded, tmp_path):
    run_id, chunks = loaded
    vectors = unit_vectors(chunks, same_unit_same_vector=False)
    write_vectors(tmp_path / "v.parquet", chunks, vectors)
    store.load_embeddings(conn, run_id, tmp_path / "v.parquet")
    hits = smoke.nearest(conn, run_id, vectors[5], k=3)
    first = conn.execute(
        "SELECT count(*) FROM chunks WHERE article_uid = %s", (chunks[5].article_uid,)
    ).fetchone()[0]
    assert (hits[0].chunk_index, hits[0].chunks) == (chunks[5].chunk_index, first)
    assert hits[0].distance == pytest.approx(0, abs=1e-5) and hits[0].distance < hits[1].distance
    assert conn.execute("SHOW hnsw.ef_search").fetchone()[0] == str(smoke.EF_SEARCH)
    labels = smoke.known_labels(conn)
    assert "L1237-1" in labels and any(label.startswith("art ") for label in labels)


def test_analyze_gives_the_planner_row_counts_after_a_load(conn, loaded):
    def estimate():
        return conn.execute("SELECT reltuples FROM pg_class WHERE relname = 'chunks'").fetchone()[0]

    assert estimate() < 0  # -1: never analysed
    store.analyze(conn)
    assert estimate() == len(loaded[1])


def test_exact_scan_skips_the_vector_index_and_restores_the_setting(conn, loaded, tmp_path):
    run_id, chunks = loaded
    write_vectors(tmp_path / "v.parquet", chunks, unit_vectors(chunks, same_unit_same_vector=False))
    store.load_embeddings(conn, run_id, tmp_path / "v.parquet")
    store.build_hnsw_index(conn)
    conn.execute("SET LOCAL enable_seqscan = off")  # a table this small would otherwise be scanned
    probe = conn.execute("SELECT embedding FROM chunk_embeddings LIMIT 1").fetchone()[0]

    def plan():
        sql = "EXPLAIN " + NEIGHBOUR_QUERY.format(extra="")
        return " ".join(r[0] for r in conn.execute(sql, (run_id, probe, 5)))

    with _exact_scan(conn):
        assert store.HNSW_INDEX not in plan()
    assert store.HNSW_INDEX in plan()
    assert conn.execute("SHOW enable_indexscan").fetchone()[0] == "on"


def test_index_recall_counts_the_exact_neighbours_the_index_returns(conn, loaded, tmp_path):
    run_id, chunks = loaded
    write_vectors(tmp_path / "v.parquet", chunks, unit_vectors(chunks, same_unit_same_vector=False))
    store.load_embeddings(conn, run_id, tmp_path / "v.parquet")
    store.build_hnsw_index(conn)
    found, possible = index_recall(conn, run_id, sample=10, k=3)
    assert possible == 30 and found == possible


def test_db_checks_run_end_to_end_on_loaded_data(conn, loaded, tmp_path):
    from legalrag.dbcheck import db_checks

    run_id, chunks = loaded
    write_vectors(tmp_path / "v.parquet", chunks, unit_vectors(chunks))
    store.load_embeddings(conn, run_id, tmp_path / "v.parquet")
    store.build_hnsw_index(conn)
    results = db_checks(conn, "t", len(chunks))
    # On a table this small the planner prefers a sequential scan, so that one check may fail.
    failing = [name for name, ok, _ in results if not ok and not name.startswith("planner")]
    assert failing == []
    assert len(results) == 11
