"""Commands on the evaluation: sanity runs, smoke, eval, compare, gold checks."""

import hashlib
import json
import time
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

from legalrag.cli.common import EMBEDDINGS, MODEL_OPTION, PARQUET, model_spec
from legalrag.corpus.sources import legi
from legalrag.evaluation import evaluate, gold, sanity, smoke
from legalrag.experiments import keyword, rerank, rewrite, sparse
from legalrag.index import db, embed

app = typer.Typer(no_args_is_help=True)


@app.command("sanity")
def sanity_cmd(
    run: Annotated[str, typer.Option(help="Run name of the embeddings file")] = "main",
    model: Annotated[str, MODEL_OPTION] = embed.BASELINE_KEY,
    device: Annotated[str, typer.Option(help="cuda, cpu or auto")] = "auto",
) -> None:
    """Rank the embedded chunks against known questions; exit 1 if an expected article misses."""
    model_spec(model)
    uids, vectors = sanity.load(EMBEDDINGS / f"{model}-{run}.parquet")
    numbers = {a.uid: a.article_num for a in legi.to_articles(legi.read(PARQUET))}
    labels = [numbers.get(u, u) for u in uids]
    results = sanity.rank(labels, vectors, embed.SentenceTransformerEmbedder(device, model_key=model))
    for r in results:
        typer.echo(f"{'PASS' if r.ok else 'FAIL'}  {r.question}  (expected {r.expected})")
        for label, score in r.hits:
            typer.echo(f"    {score:.3f}  {label}")
    raise typer.Exit(0 if all(r.ok for r in results) else 1)


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


def _sparse_search(conn, run_id: int, questions: list, sparse_file: Path, device: str) -> tuple:
    """(index, one sparse query vector per question, record for the run file) of the bge-m3 sparse search."""
    if not sparse_file.exists():
        raise typer.BadParameter(f"{sparse_file} is missing: download it from its Release (docs/handoff/bge_sparse_windows.md)")
    index = sparse.SparseIndex(pd.read_parquet(sparse_file), conn.execute(sparse.RUN_CHUNKS, (run_id,)).fetchall())
    encoder = sparse.SparseEncoder(device)
    queries = encoder.encode([q.question for q in questions])
    return index, queries, {"file_sha256": hashlib.sha256(sparse_file.read_bytes()).hexdigest(), **encoder.info()}


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
    model_name = model_spec(embedding_model).name
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
