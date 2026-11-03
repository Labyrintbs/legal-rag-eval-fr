import hashlib
import json
import os
import time
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

from legalrag import (
    db,
    dbcheck,
    embed,
    evaluate,
    fetch,
    gold,
    headsentence,
    keyword,
    llm,
    rerank,
    rewrite,
    sanity,
    smoke,
    sparse,
    store,
    trace,
    variants,
    verify,
)
from legalrag.ingest import build_chunks, token_counter
from legalrag.sources import gdpr, legi

app = typer.Typer(no_args_is_help=True)
traces_app = typer.Typer(no_args_is_help=True, help="Look at the traces of the service: failures, summary, purge, export.")
app.add_typer(traces_app, name="traces")

RAW = Path("data/raw")
PARQUET = RAW / "legi_vincegx33_train.parquet"
TOKENIZER = RAW / "bge-m3-tokenizer.json"
EMBEDDINGS = Path("data/embeddings")
SENTENCES = Path("data/sentences")
PROFILES = Path("docs/data_profiles")
SOURCES = ("legi", "gdpr")
VARIANT_OPTION = typer.Option(help="Chunking variant (names in variants.py)")
MODEL_OPTION = typer.Option(help="Embedding model key (embed.EMBEDDING_MODELS)")


def _model_spec(model: str) -> embed.ModelSpec:
    if model not in embed.EMBEDDING_MODELS:
        raise typer.BadParameter(f"unknown model {model!r}; choose from {', '.join(embed.EMBEDDING_MODELS)}")
    return embed.EMBEDDING_MODELS[model]


def _variant_settings(variant: str) -> dict:
    try:
        return variants.settings(variant)
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e


def _sentences_path(settings: dict) -> Path | None:
    return SENTENCES / f"{settings['sentences']}.jsonl" if "sentences" in settings else None


def _chunk_kwargs(settings: dict) -> dict:
    """build_chunks arguments of a variant: a sentences name becomes the sentences of its file."""
    path = _sentences_path(settings)
    if path is None:
        return settings
    if not path.exists():
        raise typer.BadParameter(f"{path} is missing: write it with scripts/heading_sentences_all.py or download it")
    return {**settings, "sentences": headsentence.load_sentences(path)}


def _sentences_sha256(settings: dict) -> str | None:
    path = _sentences_path(settings)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path else None


def _variant_chunks(variant: str, limit: int | None) -> tuple[list, dict]:
    """The chunks of a variant (Code du travail, GDPR French and English) and its recorded settings; a limit
    takes an even sample of about that many."""
    chunk_settings = _variant_settings(variant)
    kwargs = _chunk_kwargs(chunk_settings)
    count = token_counter(TOKENIZER)
    chunks = build_chunks(legi.to_articles(legi.read(PARQUET)), count, **kwargs)
    for lang in ("fr", "en"):
        chunks += build_chunks(gdpr.parse(RAW / f"gdpr_{lang}.xhtml", lang), count, **kwargs)
    if limit:
        chunks = chunks[:: max(1, len(chunks) // limit)][:limit]
    return chunks, chunk_settings


def _progress(done: int, total: int) -> None:
    typer.echo(f"encoded {done}/{total}")


def _sparse_search(conn, run_id: int, questions: list, sparse_file: Path, device: str) -> tuple:
    """(index, one sparse query vector per question, record for the run file) of the bge-m3 sparse search."""
    if not sparse_file.exists():
        raise typer.BadParameter(f"{sparse_file} is missing: download it from its Release (docs/handoff/bge_sparse_windows.md)")
    index = sparse.SparseIndex(pd.read_parquet(sparse_file), conn.execute(sparse.RUN_CHUNKS, (run_id,)).fetchall())
    encoder = sparse.SparseEncoder(device)
    queries = encoder.encode([q.question for q in questions])
    return index, queries, {"file_sha256": hashlib.sha256(sparse_file.read_bytes()).hexdigest(), **encoder.info()}


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
    variant: Annotated[str, VARIANT_OPTION] = variants.DEFAULT,
    model: Annotated[str, MODEL_OPTION] = embed.BASELINE_KEY,
    limit: Annotated[int | None, typer.Option(help="Trial: embed only about this many chunks")] = None,
    batch_size: Annotated[int, typer.Option(help="Texts per batch")] = embed.BATCH_SIZE,
    shard_size: Annotated[int, typer.Option(help="Chunks per saved shard")] = embed.SHARD_SIZE,
    device: Annotated[str, typer.Option(help="cuda, cpu or auto")] = "cuda",
) -> None:
    """Embed all chunks of a variant (GPU by default); resumes from the shards already saved."""
    spec = _model_spec(model)
    chunks, chunk_settings = _variant_chunks(variant, limit)
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
            "sentences_sha256": _sentences_sha256(chunk_settings),
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
    chunks, chunk_settings = _variant_chunks(variant, limit)
    typer.echo(f"{len(chunks)} chunks")
    encoder = sparse.SparseEncoder(device)
    started = time.monotonic()
    encoded = encoder.encode([c.embed_text for c in chunks], batch_size, progress=_progress)
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


@app.command("sanity")
def sanity_cmd(
    run: Annotated[str, typer.Option(help="Run name of the embeddings file")] = "main",
    model: Annotated[str, MODEL_OPTION] = embed.BASELINE_KEY,
    device: Annotated[str, typer.Option(help="cuda, cpu or auto")] = "auto",
) -> None:
    """Rank the embedded chunks against known questions; exit 1 if an expected article misses."""
    _model_spec(model)
    uids, vectors = sanity.load(EMBEDDINGS / f"{model}-{run}.parquet")
    numbers = {a.uid: a.article_num for a in legi.to_articles(legi.read(PARQUET))}
    labels = [numbers.get(u, u) for u in uids]
    results = sanity.rank(labels, vectors, embed.SentenceTransformerEmbedder(device, model_key=model))
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
    variant: Annotated[str, VARIANT_OPTION] = variants.DEFAULT,
    run: Annotated[str | None, typer.Option(help="Chunking run name (default: the variant name)")] = None,
    allow_dirty: Annotated[
        bool, typer.Option(help="Load from a tree with uncommitted changes (recorded as such)")
    ] = False,
) -> None:
    """Load articles and the chunks of a variant into Postgres; safe to re-run."""
    chunk_settings = _variant_settings(variant)
    kwargs = _chunk_kwargs(chunk_settings)
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
    _variant_settings(variant)
    _model_spec(model)
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


@traces_app.command("failures")
def traces_failures_cmd(
    days: Annotated[float, typer.Option(help="How far back to look")] = 7,
    outcome: Annotated[list[str] | None, typer.Option(help="Only these outcomes (default: all quality failures)")] = None,
    limit: Annotated[int, typer.Option(help="Most rows to print")] = 50,
) -> None:
    """The latest requests the system could not answer, with what retrieval found."""
    if bad := [o for o in outcome or [] if o not in trace.OUTCOMES]:
        raise typer.BadParameter(f"unknown outcome {bad}; choose from {', '.join(trace.OUTCOMES)}")
    with db.connect() as conn:
        rows = trace.failures(conn, timedelta(days=days), tuple(outcome or trace.FAILURES), limit)
    for r in rows:
        top = ", ".join(f"{x['label']} ({x.get('score', 0):.2f})" for x in r["retrieved"][:3])
        typer.echo(f"{r['created_at']:%Y-%m-%d %H:%M} {r['outcome']:<24} {r['question'][:90]!r}\n    top: {top or '-'}"
                   f"{'  | ' + r['refusal_reason'] if r['refusal_reason'] else ''}{'  | ' + r['error'] if r['error'] else ''}")
    typer.echo(f"{len(rows)} failures in the last {days:g} days")


@traces_app.command("summary")
def traces_summary_cmd(days: Annotated[float, typer.Option(help="How far back to look")] = 1) -> None:
    """Requests by outcome, share answered, tokens, cost and time of the answered ones."""
    with db.connect() as conn:
        s = trace.summary(conn, timedelta(days=days))
    typer.echo(f"{s['requests']} requests in the last {days:g} days; answered share "
               f"{'-' if s['answered_share'] is None else format(s['answered_share'], '.0%')}")
    for name, n in sorted(s["by_outcome"].items(), key=lambda x: -x[1]):
        typer.echo(f"  {name:<24} {n}")
    a = s["answered"]
    typer.echo(f"answered: {a['tokens_in']} tokens in, {a['tokens_out']} out, {a['cost_usd']:.4f} USD, "
               f"time median {a['p50_ms'] or 0:.0f} ms, 95th percentile {a['p95_ms'] or 0:.0f} ms")


@traces_app.command("purge")
def traces_purge_cmd(yes: Annotated[bool, typer.Option("--yes", help="Do not ask for confirmation")] = False) -> None:
    """Delete the traces past their 30-day expiry; asks first."""
    with db.connect() as conn:
        n = trace.expired(conn)
        typer.echo(f"{n} expired traces will be deleted.")
        if n and not yes:
            typer.confirm("Delete them?", abort=True)
        if n:
            trace.purge(conn)
    typer.echo("deleted" if n else "nothing to delete")


@traces_app.command("export")
def traces_export_cmd(
    out: Annotated[Path, typer.Argument(help="JSON lines file to write (must not exist)")],
    days: Annotated[float, typer.Option(help="How far back to look")] = 30,
) -> None:
    """Write the failures for review: candidates for the eval set, nothing in them is verified."""
    with db.connect() as conn:
        try:
            n = trace.export_candidates(conn, timedelta(days=days), out)
        except FileExistsError as e:
            raise typer.BadParameter(str(e)) from e
    typer.echo(f"{n} candidates written to {out}; read each one and remove personal data before use")


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


def _embed_texts(questions: list[gold.GoldQuestion], texts: list[str], embedder) -> list:
    """One unit-length vector per text, in the language and group of the question it stands for."""
    return smoke.embed_questions(
        [smoke.Question(id=0, group=q.group, lang=q.lang, question=t) for q, t in zip(questions, texts, strict=True)],
        embedder,
    )


@app.command("eval")
def eval_cmd(
    name: Annotated[str, typer.Option(help="Run name, used in the output file name")] = "baseline",
    split: Annotated[str, typer.Option(help="dev or test")] = "dev",
    final: Annotated[bool, typer.Option(help="Allow the test half (decision 5: once at the end of a stage)")] = False,
    file: Annotated[Path, typer.Option(help="Gold file")] = Path("eval/gold.jsonl"),
    run: Annotated[str, typer.Option(help="Chunking run name")] = "default",
    search: Annotated[str, typer.Option(help="dense, keyword or hybrid")] = "dense",
    keyword_weight: Annotated[float, typer.Option(help="Weight of the keyword list in the hybrid fusion")] = 1.0,
    reranker: Annotated[str, typer.Option(help="Cross-encoder model for --search rerank")] = rerank.DEFAULT_MODEL,
    rerank_depth: Annotated[int, typer.Option(help="Dense candidates the reranker re-orders")] = evaluate.RERANK_DEPTH,
    embedding_model: Annotated[str, MODEL_OPTION] = embed.BASELINE_KEY,
    device: Annotated[str, typer.Option(help="cuda, cpu or auto")] = "auto",
    language_filter: Annotated[bool, typer.Option(help="Keep only chunks in the question's language (dense only)")] = True,
    article_lookup: Annotated[bool, typer.Option(help="Put the articles the question names by number first")] = False,
    rewrites: Annotated[Path | None, typer.Option(help="Rewrite file of scripts/rewrite_questions.py (dense only)")] = None,
    rewrite_mode: Annotated[str, typer.Option(help="replace: search the rewrite; fuse: rewrite and original fused")] = "replace",
    lexical: Annotated[str, typer.Option(help="Word matching of keyword and hybrid: bm25, tsrank, tsrank-len or sparse")] = "bm25",
    sparse_file: Annotated[Path, typer.Option(help="Sparse vectors for --lexical sparse")] = sparse.DEFAULT_FILE,
) -> None:
    """Search on the gold questions of one half: metrics with bootstrap intervals."""
    if lexical not in ("bm25", "sparse", *keyword.TSRANK_NORMALIZATION):
        raise typer.BadParameter("lexical must be bm25, tsrank, tsrank-len or sparse")
    if not language_filter and search != "dense":
        raise typer.BadParameter("--no-language-filter works with --search dense only")
    if rewrites and search != "dense":
        raise typer.BadParameter("--rewrites works with --search dense only")
    if rewrite_mode not in ("replace", "fuse"):
        raise typer.BadParameter("rewrite mode must be replace or fuse")
    if split not in ("dev", "test"):
        raise typer.BadParameter("split must be dev or test")
    if split == "test" and not final:
        raise typer.BadParameter("the test half is for the end of a stage: add --final")
    if search not in evaluate.SEARCHES:
        raise typer.BadParameter(f"search must be one of {', '.join(evaluate.SEARCHES)}")
    model_name = _model_spec(embedding_model).name
    questions = [q for q in gold.load_gold(file) if q.split == split]
    embedder = None if search == "keyword" else embed.SentenceTransformerEmbedder(device, model_key=embedding_model)
    vectors = None if search == "keyword" else _embed_texts(questions, [q.question for q in questions], embedder)
    rewrite_vectors, rewrite_record = None, None
    if rewrites:
        used = rewrite.load_used(rewrites)
        if missing := [q.id for q in questions if q.id not in used]:
            raise typer.BadParameter(f"no rewrite for {len(missing)} questions, e.g. {missing[:3]}")
        texts = [used[q.id] for q in questions]
        embedded = _embed_texts(questions, texts, embedder)
        vectors, rewrite_vectors = (embedded, None) if rewrite_mode == "replace" else (vectors, embedded)
        rewrite_record = {"file_sha256": hashlib.sha256(rewrites.read_bytes()).hexdigest(), "mode": rewrite_mode,
                          "searched_with_rewrite": sum(t != q.question for t, q in zip(texts, questions, strict=True))}
    scorer = rerank.make_scorer(reranker, device) if search == "rerank" else None
    with db.connect() as conn:
        row = conn.execute("SELECT id FROM chunking_runs WHERE name = %s", (run,)).fetchone()
        if row is None:
            raise typer.BadParameter(f"no chunking run named {run!r}")
        sparse_index, sparse_queries, sparse_record = (
            _sparse_search(conn, row[0], questions, sparse_file, device)
            if lexical == "sparse" and search in ("keyword", "hybrid") else (None, None, None)
        )
        started = time.monotonic()
        retrieved = evaluate.retrieve_all(
            conn, row[0], questions, vectors, search, keyword_weight, scorer, rerank_depth, model_name, language_filter,
            article_lookup, rewrite_vectors, lexical, sparse_index, sparse_queries,
        )
        search_seconds = time.monotonic() - started
    rows = evaluate.score(questions, retrieved)
    typer.echo(evaluate.format_summary(f"{name} {split}", evaluate.summarize(rows)))
    for key in ("group", "kind"):
        for value, part in evaluate.by(rows, key).items():
            typer.echo(evaluate.format_summary(f"  {key} {value}", evaluate.summarize(part)))
    out = Path("data/runs") / f"{name}_{split}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    settings = evaluate.settings(file, split, run, search, keyword_weight, model_name, language_filter, article_lookup,
                                rewrite_record, lexical, sparse_record)
    # the search step only: query embedding and model loading are left out
    settings["search_seconds_per_question"] = round(search_seconds / len(questions), 3)
    typer.echo(f"search time {settings['search_seconds_per_question']} s per question")
    if scorer:
        settings["reranker"] = {**scorer.info(), "depth": rerank_depth}
    out.write_text(json.dumps({"settings": settings, "rows": rows}, ensure_ascii=False, indent=1))
    typer.echo(f"written {out}")


@app.command("compare")
def compare_cmd(
    base: Annotated[str, typer.Argument(help="Run name of the reference, e.g. baseline")],
    other: Annotated[str, typer.Argument(help="Run name to compare with it")],
    split: Annotated[str, typer.Option(help="dev or test")] = "dev",
) -> None:
    """Paired difference (other minus base) of every metric, with the decision 3b verdict."""
    runs = []
    for name in (base, other):
        path = Path("data/runs") / f"{name}_{split}.json"
        if not path.exists():
            raise typer.BadParameter(f"no run file {path}")
        runs.append(json.loads(path.read_text()))
    try:
        diff = evaluate.compare(*runs)
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e
    typer.echo(evaluate.format_diff(f"{other} minus {base} ({split})", diff))
    for group in sorted({r["group"] for r in runs[0]["rows"]}):
        parts = [{"settings": run["settings"], "rows": [r for r in run["rows"] if r["group"] == group]} for run in runs]
        if not any(r["metrics"] for r in parts[0]["rows"]):
            continue
        mean, low, high = evaluate.compare(*parts)["metrics"]["ndcg@10"]
        count = sum(bool(r["metrics"]) for r in parts[0]["rows"])
        typer.echo(f"  group {group}: {count} questions, nDCG@10 {mean:+.3f} [{low:+.3f}, {high:+.3f}]")


@app.command("gold-check")
def gold_check_cmd(
    file: Annotated[Path, typer.Option(help="Gold file")] = Path("eval/gold.jsonl"),
) -> None:
    """Check that every gold article is in the database with the text it was labelled against."""
    questions = gold.load_gold(file)
    with db.connect() as conn:
        problems = gold.check_hashes(questions, gold.article_hashes(conn))
    flagged = sum(q.review.status == "needs_review" for q in questions)
    typer.echo(f"{len(questions)} questions, {sum(len(q.gold) for q in questions)} gold articles, "
               f"{flagged} marked needs_review")
    for group, halves in gold.split_counts(questions).items():
        typer.echo(f"group {group}: dev {halves['dev']}, test {halves['test']}")
    for p in problems:
        typer.echo(f"PROBLEM  {p}")
    raise typer.Exit(1 if problems else 0)


@app.command("gold-qrels")
def gold_qrels_cmd(
    file: Annotated[Path, typer.Option(help="Gold file")] = Path("eval/gold.jsonl"),
    out: Annotated[Path, typer.Option(help="TREC qrels file")] = Path("eval/gold.qrels"),
) -> None:
    """Export the gold as TREC qrels (query id, 0, article label, grade), for ir_measures."""
    out.write_text(gold.format_qrels(gold.to_qrels(gold.load_gold(file))))
    typer.echo(f"written {out}")


@app.command("llm-balance")
def llm_balance_cmd(
    label: Annotated[str, typer.Option(help="Name of this snapshot, e.g. before-pilot")] = "",
) -> None:
    """Read the DeepSeek balance and record it in the ledger (needs DEEPSEEK_API_KEY)."""
    with llm.make_http(os.environ["DEEPSEEK_API_KEY"]) as http:
        balances = llm.balance(http)
    llm.record_balance(llm.LEDGER, balances, label)
    typer.echo(", ".join(f"{amount:.2f} {currency}" for currency, amount in balances.items()))


@app.command("llm-ledger")
def llm_ledger_cmd() -> None:
    """Spend so far, and the last two balance snapshots against the cost estimated between them."""
    calls = [e for e in llm.read_ledger(llm.LEDGER) if e["type"] == "call"]
    typer.echo(f"{len(calls)} calls, {llm.ledger_total(llm.LEDGER):.4f} USD estimated")
    result = llm.reconcile(llm.LEDGER)
    if result is None:
        typer.echo("fewer than two balance snapshots: run llm-balance before and after a run")
        return
    drop = ", ".join(f"{amount:.4f} {currency}" for currency, amount in result["balance_drop"].items())
    typer.echo(f"between the last two snapshots: {result['calls']} calls, "
               f"{result['estimated_usd']:.4f} USD estimated, balance dropped {drop}")


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
