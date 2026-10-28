"""Evaluation run: retrieve for each gold question, merge chunks to articles, score, summarise.

Baseline settings (decision 1): dense search only, exact (no vector index), chunks filtered to the
question's language. The ranking is by article: the best chunk of an article places it.
"""

import hashlib
import subprocess
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from legalrag import gold, metrics
from legalrag.dbcheck import _exact_scan
from legalrag.embed import MODEL
from legalrag.smoke import article_label

ARTICLES_KEPT = 20  # the deepest cut-off reported (Recall@20)
CHUNKS_SEARCHED = 400  # enough chunks to find 20 distinct articles when some are split in many chunks
EXACT_SEARCH = (
    "SELECT a.source_code, a.kind, a.article_num, a.content_hash "
    "FROM chunk_embeddings e JOIN chunks c ON c.id = e.chunk_id JOIN articles a ON a.uid = c.article_uid "
    "WHERE e.model = %s AND c.run_id = %s AND c.lang = %s ORDER BY e.embedding <=> %s LIMIT %s"
)


def merge_chunks(rows: list[tuple[str, str, str, str]], keep: int = ARTICLES_KEPT) -> list[tuple[str, str]]:
    """(label, content hash) of the first `keep` distinct articles, in the order of their best chunk."""
    seen: dict[str, str] = {}
    for source, kind, num, body_hash in rows:
        seen.setdefault(article_label(source, kind, num), body_hash)
        if len(seen) == keep:
            break
    return list(seen.items())


def retrieve(conn: psycopg.Connection, run_id: int, lang: str, vector) -> list[tuple[str, str]]:
    with _exact_scan(conn):
        rows = conn.execute(EXACT_SEARCH, (MODEL, run_id, lang, vector, CHUNKS_SEARCHED)).fetchall()
    return merge_chunks(rows)


def score(questions: list[gold.GoldQuestion], retrieved: dict[str, list[tuple[str, str]]]) -> list[dict]:
    """One row per question: the ranking and, for questions that have gold, the metrics."""
    cluster_of = gold.clusters(questions)
    rows = []
    for q in questions:
        ranked = retrieved[q.id]
        row = {"id": q.id, "group": q.group, "kind": q.kind, "split": q.split, "cluster": cluster_of[q.id],
               "ranked": [label for label, _ in ranked], "metrics": None}
        if q.gold:
            gold_items = [(g.article, g.content_hash, g.grade) for g in q.gold]
            row["metrics"] = metrics.question_metrics(metrics.match_ranking(ranked, gold_items))
        rows.append(row)
    return rows


def summarize(rows: list[dict], select=lambda r: True) -> dict | None:
    """Mean and 95% interval of every metric over the selected questions that have gold
    (unanswerable questions are left out, decision 3)."""
    chosen = [r for r in rows if r["metrics"] and select(r)]
    if not chosen:
        return None
    clusters = [r["cluster"] for r in chosen]
    return {
        "questions": len(chosen), "clusters": len(set(clusters)),
        "metrics": {name: metrics.bootstrap_ci([r["metrics"][name] for r in chosen], clusters)
                    for name in metrics.METRICS},
    }


def format_summary(title: str, summary: dict | None) -> str:
    if summary is None:
        return f"{title}: no question with gold"
    head = f"{title}: {summary['questions']} questions, {summary['clusters']} clusters"
    cells = "  ".join(f"{name} {mean:.3f} [{low:.3f}-{high:.3f}]"
                      for name, (mean, low, high) in summary["metrics"].items())
    return f"{head}\n  {cells}"


def settings(gold_path: Path, split: str, chunking_run: str) -> dict:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True).stdout)
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, None
    return {
        "date": datetime.now(UTC).isoformat(timespec="seconds"), "git_commit": commit, "uncommitted_changes": dirty,
        "split": split,
        "gold_sha256": hashlib.sha256(gold_path.read_bytes()).hexdigest(), "chunking_run": chunking_run,
        "embedding_model": MODEL, "search": "dense, exact (no vector index)", "language_filter": True,
        "unit": "article (best chunk), top 20", "ndcg_gain": "linear (the grade)",
        "bootstrap": "2000 resamples of clusters, 95% percentile interval",
    }


def by(rows: list[dict], key: str) -> dict[str, list[dict]]:
    grouped = defaultdict(list)
    for r in rows:
        grouped[r[key]].append(r)
    return dict(sorted(grouped.items()))
