"""Commands on the index: embed, load chunks and vectors, migrate, check, delete a run."""

import time
from collections import Counter
from pathlib import Path
from typing import Annotated

import typer

from legalrag.cli.common import (
    EMBEDDINGS,
    MODEL_OPTION,
    PARQUET,
    RAW,
    TOKENIZER,
    VARIANT_OPTION,
    chunk_kwargs,
    model_spec,
    progress,
    sentences_sha256,
    variant_chunks,
    variant_settings,
)
from legalrag.corpus import variants
from legalrag.corpus.ingest import build_chunks, token_counter
from legalrag.corpus.sources import gdpr, legi
from legalrag.experiments import sparse
from legalrag.index import db, dbcheck, embed, store

app = typer.Typer(no_args_is_help=True)


@app.command("embed")
def embed_cmd(
    variant: Annotated[str, VARIANT_OPTION] = variants.DEFAULT,
    model: Annotated[str, MODEL_OPTION] = embed.BASELINE_KEY,
    limit: Annotated[int | None, typer.Option(help="Trial: embed only about this many chunks")] = None,
    batch_size: Annotated[int, typer.Option(help="Texts per batch")] = embed.BATCH_SIZE,
    shard_size: Annotated[int, typer.Option(help="Chunks per saved shard")] = embed.SHARD_SIZE,
    device: Annotated[str, typer.Option(help="cuda, cpu or auto")] = "cuda",
) -> None:
    """Embed all chunks of a variant (GPU by default); resumes from the shards already saved."""
    spec = model_spec(model)
    chunks, chunk_settings = variant_chunks(variant, limit)
    typer.echo(f"{len(chunks)} chunks")

    embedder = embed.SentenceTransformerEmbedder(device, model_key=model)
    name = variants.embeddings_name(variant, model)
    shard_dir = EMBEDDINGS / name
    started = time.monotonic()
    computed = embed.embed_chunks(
        chunks, embedder, shard_dir, shard_size, batch_size, spec.max_seq_length,
        progress=lambda done, total: typer.echo(f"embedded {done}/{total}"),
    )
    seconds = round(time.monotonic() - started)
    info = embedder.info()
    rows = embed.merge_shards(
        chunks, shard_dir, EMBEDDINGS / f"{name}.parquet", spec.name, info["model_revision"]
    )
    embed.write_run_json(
        EMBEDDINGS / f"{name}.run.json",
        {
            **info,
            "git_commit": embed.git_commit(),
            "variant": variant,
            "model_key": model,
            "limit": limit,
            "chunk_settings": chunk_settings,
            "sentences_sha256": sentences_sha256(chunk_settings),
            "batch_size": batch_size,
            "max_seq_length": spec.max_seq_length,
            "rows": rows,
            "computed_in_this_invocation": computed,
            "seconds_this_invocation": seconds,
            "rows_by_corpus": dict(Counter(c.article_uid.rpartition(":")[0] for c in chunks)),
        },
    )
    typer.echo(f"{rows} rows written, {computed} computed in {seconds}s")


@app.command("sparse-embed")
def sparse_embed_cmd(
    variant: Annotated[str, VARIANT_OPTION] = variants.DEFAULT,
    limit: Annotated[int | None, typer.Option(help="Trial: only about this many chunks")] = None,
    batch_size: Annotated[int, typer.Option(help="Texts per batch")] = sparse.BATCH_SIZE,
    device: Annotated[str, typer.Option(help="cuda, cpu or auto")] = "cuda",
) -> None:
    """Write the bge-m3 sparse (word weight) vector of every chunk of a variant (GPU by default)."""
    chunks, chunk_settings = variant_chunks(variant, limit)
    typer.echo(f"{len(chunks)} chunks")
    encoder = sparse.SparseEncoder(device)
    started = time.monotonic()
    encoded = encoder.encode([c.embed_text for c in chunks], batch_size, progress=progress)
    seconds = round(time.monotonic() - started)
    path = EMBEDDINGS / f"bge-m3-sparse-{variant}.parquet"
    sparse.write(path, chunks, encoded)
    embed.write_run_json(path.with_suffix(".run.json"), {
        **encoder.info(), "git_commit": embed.git_commit(), "variant": variant, "limit": limit,
        "chunk_settings": chunk_settings, "batch_size": batch_size, "rows": len(chunks), "seconds": seconds,
        "tokens_per_chunk_mean": round(sum(len(ids) for ids, _ in encoded) / len(encoded), 1),
        "rows_by_corpus": dict(Counter(c.article_uid.rpartition(":")[0] for c in chunks)),
    })
    typer.echo(f"{len(chunks)} rows written in {seconds}s")


@app.command("migrate")
def migrate_cmd() -> None:
    """Create or update the database schema (DATABASE_URL)."""
    db.migrate()
    typer.echo("schema up to date")


def _all_articles() -> dict[tuple[str, str], list]:
    return {
        ("code_travail", "fr"): legi.to_articles(legi.read(PARQUET)),
        ("rgpd", "fr"): gdpr.parse(RAW / "gdpr_fr.xhtml", "fr"),
        ("rgpd", "en"): gdpr.parse(RAW / "gdpr_en.xhtml", "en"),
    }


@app.command("load-chunks")
def load_chunks_cmd(
    variant: Annotated[str, VARIANT_OPTION] = variants.DEFAULT,
    run: Annotated[str | None, typer.Option(help="Chunking run name (default: the variant name)")] = None,
    allow_dirty: Annotated[
        bool, typer.Option(help="Load from a tree with uncommitted changes (recorded as such)")
    ] = False,
) -> None:
    """Load articles and the chunks of a variant into Postgres; safe to re-run."""
    chunk_settings = variant_settings(variant)
    kwargs = chunk_kwargs(chunk_settings)
    run = run or variant
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
            conn, run, chunk_settings, "BAAI/bge-m3",
            "code_travail: sentences; rgpd: paragraphs, then points, then sentences",
            commit,
        )
        chunks = [c for arts in corpora.values() for c in build_chunks(arts, count, **kwargs)]
        inserted = store.load_chunks(conn, run_id, chunks)
    typer.echo(f"{sum(len(a) for a in corpora.values())} articles, {inserted} new chunks of {len(chunks)}")


@app.command("load-embeddings")
def load_embeddings_cmd(
    variant: Annotated[str, VARIANT_OPTION] = variants.DEFAULT,
    model: Annotated[str, MODEL_OPTION] = embed.BASELINE_KEY,
    file: Annotated[Path | None, typer.Option(help="Vectors file from `embed` (default: the model's file)")] = None,
    run: Annotated[str | None, typer.Option(help="Chunking run name (default: the variant name)")] = None,
) -> None:
    """Load the vectors of a variant and model and build the vector index."""
    variant_settings(variant)
    model_spec(model)
    file = file or EMBEDDINGS / f"{variants.embeddings_name(variant, model)}.parquet"
    run = run or variant
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
