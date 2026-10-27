import time
from collections import Counter
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

from legalrag import db, dbcheck, embed, fetch, sanity, smoke, store, verify
from legalrag.ingest import build_chunks, token_counter
from legalrag.sources import gdpr, legi

app = typer.Typer(no_args_is_help=True)

RAW = Path("data/raw")
PARQUET = RAW / "legi_vincegx33_train.parquet"
TOKENIZER = RAW / "bge-m3-tokenizer.json"
EMBEDDINGS = Path("data/embeddings")
PROFILES = Path("docs/data_profiles")
SOURCES = ("legi", "gdpr")
# The decided defaults (EXPERIMENT.md); they define the chunk set that gets embedded.
# style "last_k": header shows only the last k section titles; max_tokens: split above it;
# collapse_repeats: merge consecutive same-label levels (see chunking/header.py).
CHUNK_SETTINGS = {"style": "last_k", "k": 3, "max_tokens": 1024, "collapse_repeats": False}


def _check_source(source: str) -> None:
    if source not in SOURCES:
        raise typer.BadParameter(f"source must be one of {SOURCES}")


@app.command("fetch")
def fetch_cmd(
    source: Annotated[str, typer.Argument(help="legi, gdpr, tokenizer or all")] = "all",
    dest: Annotated[Path, typer.Option(help="Folder for the raw files")] = RAW,
) -> None:
    """Download raw files into data/raw and check their SHA-256 (skips files already correct)."""
    names = list(fetch.SOURCES) if source == "all" else [source]
    if any(n not in fetch.SOURCES for n in names):
        raise typer.BadParameter(f"source must be one of {[*fetch.SOURCES, 'all']}")
    failed = False
    for name in names:
        for f in fetch.SOURCES[name]:
            try:
                typer.echo(f"{fetch.fetch_file(f, dest):<10} {f.name}")
            except (fetch.ChecksumError, OSError) as e:
                typer.echo(f"FAILED     {f.name}: {e}")
                failed = True
    raise typer.Exit(1 if failed else 0)


@app.command("embed")
def embed_cmd(
    run: Annotated[str, typer.Option(help="Run name, used in the output file names")] = "main",
    limit: Annotated[int | None, typer.Option(help="Trial: embed only about this many chunks")] = None,
    batch_size: Annotated[int, typer.Option(help="Texts per batch")] = embed.BATCH_SIZE,
    shard_size: Annotated[int, typer.Option(help="Chunks per saved shard")] = embed.SHARD_SIZE,
    device: Annotated[str, typer.Option(help="cuda, cpu or auto")] = "cuda",
) -> None:
    """Embed all chunks with bge-m3 (GPU by default); resumes from the shards already saved."""
    count = token_counter(TOKENIZER)
    chunks = build_chunks(legi.to_articles(legi.read(PARQUET)), count, **CHUNK_SETTINGS)
    for lang in ("fr", "en"):
        chunks += build_chunks(gdpr.parse(RAW / f"gdpr_{lang}.xhtml", lang), count, **CHUNK_SETTINGS)
    if limit:
        chunks = chunks[:: max(1, len(chunks) // limit)][:limit]
    typer.echo(f"{len(chunks)} chunks")

    embedder = embed.SentenceTransformerEmbedder(device)
    name = f"bge-m3-{run}"
    shard_dir = EMBEDDINGS / name
    started = time.monotonic()
    computed = embed.embed_chunks(
        chunks, embedder, shard_dir, shard_size, batch_size,
        progress=lambda done, total: typer.echo(f"embedded {done}/{total}"),
    )
    seconds = round(time.monotonic() - started)
    info = embedder.info()
    rows = embed.merge_shards(
        chunks, shard_dir, EMBEDDINGS / f"{name}.parquet", embed.MODEL, info["model_revision"]
    )
    embed.write_run_json(
        EMBEDDINGS / f"{name}.run.json",
        {
            **info,
            "git_commit": embed.git_commit(),
            "chunk_settings": CHUNK_SETTINGS,
            "batch_size": batch_size,
            "max_seq_length": embed.MAX_SEQ_LENGTH,
            "rows": rows,
            "computed_in_this_invocation": computed,
            "seconds_this_invocation": seconds,
            "rows_by_corpus": dict(Counter(c.article_uid.rpartition(":")[0] for c in chunks)),
        },
    )
    typer.echo(f"{rows} rows written, {computed} computed in {seconds}s")


@app.command("sanity")
def sanity_cmd(
    run: Annotated[str, typer.Option(help="Run name of the embeddings file")] = "main",
    device: Annotated[str, typer.Option(help="cuda, cpu or auto")] = "auto",
) -> None:
    """Rank the embedded chunks against known questions; exit 1 if an expected article misses."""
    uids, vectors = sanity.load(EMBEDDINGS / f"bge-m3-{run}.parquet")
    numbers = {a.uid: a.article_num for a in legi.to_articles(legi.read(PARQUET))}
    labels = [numbers.get(u, u) for u in uids]
    results = sanity.rank(labels, vectors, embed.SentenceTransformerEmbedder(device))
    for r in results:
        typer.echo(f"{'PASS' if r.ok else 'FAIL'}  {r.question}  (expected {r.expected})")
        for label, score in r.hits:
            typer.echo(f"    {score:.3f}  {label}")
    raise typer.Exit(0 if all(r.ok for r in results) else 1)


def _all_articles() -> dict[tuple[str, str], list]:
    return {
        ("code_travail", "fr"): legi.to_articles(legi.read(PARQUET)),
        ("rgpd", "fr"): gdpr.parse(RAW / "gdpr_fr.xhtml", "fr"),
        ("rgpd", "en"): gdpr.parse(RAW / "gdpr_en.xhtml", "en"),
    }


@app.command("migrate")
def migrate_cmd() -> None:
    """Create or update the database schema (DATABASE_URL)."""
    db.migrate()
    typer.echo("schema up to date")


@app.command("load-chunks")
def load_chunks_cmd(
    run: Annotated[str, typer.Option(help="Chunking run name")] = "default",
    allow_dirty: Annotated[
        bool, typer.Option(help="Load from a tree with uncommitted changes (recorded as such)")
    ] = False,
) -> None:
    """Load articles and chunks (default chunk settings) into Postgres; safe to re-run."""
    commit = embed.git_commit()
    # A stored run is never changed, so its code_version must name the exact code that made it.
    if commit.endswith(embed.DIRTY) and not allow_dirty:
        typer.echo("Uncommitted changes: commit first, or pass --allow-dirty to record the flag.")
        raise typer.Exit(1)
    count = token_counter(TOKENIZER)
    corpora = _all_articles()
    with db.connect() as conn:
        for (code, lang), articles in corpora.items():
            corpus_id = store.register_corpus(conn, code, lang, RAW, len(articles))
            store.load_articles(conn, articles, corpus_id)
        run_id = store.get_or_create_run(
            conn, run, CHUNK_SETTINGS, "BAAI/bge-m3",
            "code_travail: sentences; rgpd: paragraphs, then points, then sentences",
            commit,
        )
        chunks = [c for arts in corpora.values() for c in build_chunks(arts, count, **CHUNK_SETTINGS)]
        inserted = store.load_chunks(conn, run_id, chunks)
    typer.echo(f"{sum(len(a) for a in corpora.values())} articles, {inserted} new chunks of {len(chunks)}")


@app.command("load-embeddings")
def load_embeddings_cmd(
    file: Annotated[Path, typer.Option(help="Vectors file from `embed`")] = EMBEDDINGS / "bge-m3-main.parquet",
    run: Annotated[str, typer.Option(help="Chunking run name")] = "default",
) -> None:
    """Load the vectors and build the vector index."""
    with db.connect() as conn:
        run_id = conn.execute("SELECT id FROM chunking_runs WHERE name = %s", (run,)).fetchone()
        if run_id is None:
            raise typer.BadParameter(f"no chunking run named {run!r}; run load-chunks first")
        rows = store.load_embeddings(conn, run_id[0], file)
        store.build_hnsw_index(conn)
        store.analyze(conn)
    typer.echo(f"{rows} vectors loaded, index {store.HNSW_INDEX} ready")


@app.command("delete-run")
def delete_run_cmd(
    name: Annotated[str, typer.Argument(help="Chunking run name")],
    yes: Annotated[bool, typer.Option("--yes", help="Do not ask for confirmation")] = False,
) -> None:
    """Delete a chunking run with its chunks and vectors (articles stay); asks first."""
    with db.connect() as conn:
        size = store.run_size(conn, name)
        if size is None:
            raise typer.BadParameter(f"no chunking run named {name!r}")
        typer.echo(f"Run {name!r}: {size[0]} chunks and {size[1]} vectors will be deleted.")
        if not yes:
            typer.confirm("Delete them?", abort=True)
        store.delete_run(conn, name)
    typer.echo("deleted")


@app.command("db-check")
def db_check_cmd(
    run: Annotated[str, typer.Option(help="Chunking run name")] = "default",
    expected_chunks: Annotated[int, typer.Option(help="Expected chunk count")] = 12_136,
) -> None:
    """Check what is stored in Postgres: counts, vectors, index use."""
    with db.connect() as conn:
        results = dbcheck.db_checks(conn, run, expected_chunks)
    for name, ok, detail in results:
        typer.echo(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
    raise typer.Exit(0 if all(ok for _, ok, _ in results) else 1)


@app.command("smoke")
def smoke_cmd(
    file: Annotated[Path, typer.Option(help="Questions file")] = Path("tests/smoke_questions.yaml"),
    run: Annotated[str, typer.Option(help="Chunking run name")] = "default",
    k: Annotated[int, typer.Option(help="Chunks listed per question")] = 5,
    device: Annotated[str, typer.Option(help="cuda, cpu or auto")] = "auto",
) -> None:
    """Print the nearest chunks of each smoke question: an inspection, not a metric."""
    questions = smoke.load_questions(file)
    vectors = smoke.embed_questions(questions, embed.SentenceTransformerEmbedder(device))
    with db.connect() as conn:
        row = conn.execute("SELECT id FROM chunking_runs WHERE name = %s", (run,)).fetchone()
        if row is None:
            raise typer.BadParameter(f"no chunking run named {run!r}; run load-chunks first")
        unknown = sorted({e for q in questions for e in q.expected} - smoke.known_labels(conn))
        if unknown:
            typer.echo(f"WARNING: expected articles not in the database: {unknown}\n")
        ranks = {}
        for q, vector in zip(questions, vectors, strict=True):
            hits = smoke.nearest(conn, row[0], vector, k)
            ranks[q.id] = smoke.first_hit_rank(hits, q.expected)
            typer.echo(smoke.format_result(q, hits) + "\n")
    expected = [q for q in questions if q.expected]
    found = sum(ranks[q.id] is not None for q in expected)
    typer.echo(f"Expected article in the top {k}: {found} of {len(expected)} questions that have one.")
    typer.echo("First rank per question: " + ", ".join(f"Q{i}={r or '-'}" for i, r in ranks.items()))


@app.command()
def profile(source: str) -> None:
    """Write the data profile of a source (legi or gdpr)."""
    _check_source(source)
    if source == "legi":
        total = len(pd.read_parquet(PARQUET, columns=["article_id"]))
        out = legi.profile(legi.read(PARQUET), TOKENIZER, total)
        (PROFILES / "code_travail.md").write_text(out)
    else:
        out = gdpr.profile(RAW / "gdpr_fr.xhtml", RAW / "gdpr_en.xhtml", TOKENIZER)
        (PROFILES / "gdpr.md").write_text(out)
    typer.echo(out)


def _write_spot_check(path: Path, title: str, rows: list[str], header: str) -> None:
    # Holds the user's manual results; never overwrite.
    if path.exists():
        return
    path.write_text(f"# {title}\n\n{header}\n\n| Unit | URL | Body start | Result |\n|---|---|---|---|\n"
                    + "\n".join(rows) + "\n")


@app.command("verify")
def verify_cmd(source: str) -> None:
    """Run the checks of a source (legi or gdpr) and write its spot-check list if missing."""
    _check_source(source)
    count = token_counter(TOKENIZER)
    if source == "legi":
        articles = legi.to_articles(legi.read(PARQUET))
        chunks = build_chunks(articles, count)
        typer.echo(f"{len(articles)} articles, {len(chunks)} chunks")
        results = verify.verify_legi(articles, chunks, count)
        rows = [
            f"| {a.article_num} | {a.source_url} | {a.body_text[:80]} | |"
            for a in verify.spot_check_sample(articles)
        ]
        _write_spot_check(
            PROFILES / "spot_check_code_travail.md", "Spot check: Code du travail", rows,
            "20 articles drawn with a fixed seed.",
        )
    else:
        arts = {lang: gdpr.parse(RAW / f"gdpr_{lang}.xhtml", lang) for lang in ("fr", "en")}
        chunks = {lang: build_chunks(a, count) for lang, a in arts.items()}
        for lang, a in arts.items():
            typer.echo(f"{lang}: {len(a)} units, {len(chunks[lang])} chunks")
        results = verify.verify_gdpr(arts, chunks, count)
        fr = arts["fr"]
        sample = verify.spot_check_sample([a for a in fr if a.kind == "article"], 10) + \
            verify.spot_check_sample([a for a in fr if a.kind == "recital"], 5)
        rows = [
            f"| {'article' if a.kind == 'article' else 'recital'} {a.article_num} | {a.source_url} "
            f"| {a.body_text[:80].replace(chr(10), ' ')} | |"
            for a in sample
        ]
        _write_spot_check(
            PROFILES / "spot_check_gdpr.md", "Spot check: GDPR (French)", rows,
            "10 articles and 5 recitals drawn with a fixed seed. Compare with EUR-Lex "
            "(the page lists the whole regulation; search for the number).",
        )
    for name, ok, detail in results:
        typer.echo(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
    raise typer.Exit(0 if all(ok for _, ok, _ in results) else 1)
