import time
from collections import Counter
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

from legalrag import embed, fetch, verify
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
    batch_size: Annotated[int, typer.Option(help="Texts per GPU batch")] = embed.BATCH_SIZE,
    shard_size: Annotated[int, typer.Option(help="Chunks per saved shard")] = embed.SHARD_SIZE,
) -> None:
    """Embed all chunks with bge-m3 on the GPU; resumes from the shards already saved."""
    count = token_counter(TOKENIZER)
    chunks = build_chunks(legi.to_articles(legi.read(PARQUET)), count, **CHUNK_SETTINGS)
    for lang in ("fr", "en"):
        chunks += build_chunks(gdpr.parse(RAW / f"gdpr_{lang}.xhtml", lang), count, **CHUNK_SETTINGS)
    if limit:
        chunks = chunks[:: max(1, len(chunks) // limit)][:limit]
    typer.echo(f"{len(chunks)} chunks")

    embedder = embed.SentenceTransformerEmbedder()
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
