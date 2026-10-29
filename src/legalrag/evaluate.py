"""Evaluation run: retrieve for each gold question, merge chunks to articles, score, summarise.

Baseline settings (decision 1): dense search only, exact (no vector index), chunks filtered to the
question's language. The ranking is by article: the best chunk of an article places it.
Step 0c adds keyword search (BM25) and the two fused by reciprocal rank.
"""

import hashlib
import subprocess
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from legalrag import gold, keyword, metrics
from legalrag.dbcheck import _exact_scan
from legalrag.embed import MODEL
from legalrag.smoke import article_label

ARTICLES_KEPT = 20  # the deepest cut-off reported (Recall@20)
CHUNKS_SEARCHED = 400  # enough chunks to find 20 distinct articles when some are split in many chunks
SEARCHES = ("dense", "keyword", "hybrid")
FUSION_DEPTH = 100  # articles each search hands to the fusion
RRF_K = 60  # reciprocal rank fusion constant (Cormack et al., SIGIR 2009; unverified from memory)
SEARCH_TEXT = {
    "dense": "dense, exact (no vector index)",
    "keyword": f"keyword, BM25 (k1={keyword.K1}, b={keyword.B}) on the Postgres lexemes of the chunk text",
    "hybrid": f"dense + keyword, reciprocal rank fusion (k={RRF_K}) of the top {FUSION_DEPTH} articles of each",
}
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


def retrieve(
    conn: psycopg.Connection, run_id: int, lang: str, vector, keep: int = ARTICLES_KEPT
) -> list[tuple[str, str]]:
    with _exact_scan(conn):
        rows = conn.execute(EXACT_SEARCH, (MODEL, run_id, lang, vector, CHUNKS_SEARCHED)).fetchall()
    return merge_chunks(rows, keep)


def retrieve_keyword(
    conn: psycopg.Connection, index: keyword.Bm25Index, lang: str, text: str, keep: int = ARTICLES_KEPT
) -> list[tuple[str, str]]:
    rows = index.search(keyword.query_lexemes(conn, lang, text), CHUNKS_SEARCHED)
    return merge_chunks(rows, keep)


def fuse(
    rankings: list[list[tuple[str, str]]], keep: int = ARTICLES_KEPT, k: int = RRF_K,
    weights: list[float] | None = None,
) -> list[tuple[str, str]]:
    """Reciprocal rank fusion: an article scores the sum of weight / (k + rank) over the lists that hold it."""
    score: dict[str, float] = {}
    body_hash: dict[str, str] = {}
    first_seen: dict[str, int] = {}  # tiebreak: equal scores keep the order of the lists, the first list first
    for ranking, weight in zip(rankings, weights or [1.0] * len(rankings), strict=True):
        for rank, (label, h) in enumerate(ranking, 1):
            score[label] = score.get(label, 0.0) + weight / (k + rank)
            body_hash.setdefault(label, h)
            first_seen.setdefault(label, len(first_seen))
    best = sorted(score, key=lambda label: (-score[label], first_seen[label]))[:keep]
    return [(label, body_hash[label]) for label in best]


def retrieve_all(
    conn: psycopg.Connection, run_id: int, questions: list[gold.GoldQuestion], vectors, search: str,
    keyword_weight: float = 1.0,
) -> dict[str, list[tuple[str, str]]]:
    """Ranked articles for every question with the chosen search (vectors are needed unless keyword).
    keyword_weight is the weight of the keyword list in the fusion (the dense list has weight 1)."""
    indexes = {} if search == "dense" else {
        lang: keyword.Bm25Index.build(conn, run_id, lang) for lang in {q.lang for q in questions}
    }
    depth = FUSION_DEPTH if search == "hybrid" else ARTICLES_KEPT
    retrieved = {}
    for i, q in enumerate(questions):
        rankings = []
        if search in ("dense", "hybrid"):
            rankings.append(retrieve(conn, run_id, q.lang, vectors[i], depth))
        if search in ("keyword", "hybrid"):
            rankings.append(retrieve_keyword(conn, indexes[q.lang], q.lang, q.question, depth))
        retrieved[q.id] = fuse(rankings, weights=[1.0, keyword_weight]) if search == "hybrid" else rankings[0]
    return retrieved


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


def compare(base: dict, other: dict) -> dict:
    """Paired difference (other minus base) of every metric, from two saved run files, on the
    questions that have gold in both. Refuses runs scored on different gold or on different halves."""
    for key in ("gold_sha256", "split"):
        if base["settings"][key] != other["settings"][key]:
            raise ValueError(f"the runs differ in {key}")
    a = {r["id"]: r for r in base["rows"] if r["metrics"]}
    b = {r["id"]: r for r in other["rows"] if r["metrics"]}
    if a.keys() != b.keys():
        raise ValueError("the runs do not cover the same questions")
    ids = sorted(a)
    clusters = [a[i]["cluster"] for i in ids]
    return {
        "questions": len(ids), "clusters": len(set(clusters)),
        "metrics": {name: metrics.bootstrap_diff([a[i]["metrics"][name] for i in ids],
                                                 [b[i]["metrics"][name] for i in ids], clusters)
                    for name in metrics.METRICS},
    }


def verdict(diff: dict) -> str:
    """Decision 3b: nDCG@10 must rise and Recall@10 must not fall by more than its interval.
    'Clearly' means the 95% paired interval excludes 0."""
    _, n_low, n_high = diff["metrics"]["ndcg@10"]
    r_high = diff["metrics"]["recall@10"][2]
    ndcg = "clearly up" if n_low > 0 else "clearly down" if n_high < 0 else "not clearly changed"
    recall = "clearly down" if r_high < 0 else "not clearly down"
    ok = n_low > 0 and r_high >= 0
    return f"nDCG@10 {ndcg}, Recall@10 {recall}: {'improvement' if ok else 'not an improvement'} by decision 3b"


def format_diff(title: str, diff: dict) -> str:
    cells = "  ".join(f"{name} {mean:+.3f} [{low:+.3f}, {high:+.3f}]"
                      for name, (mean, low, high) in diff["metrics"].items())
    return f"{title}: {diff['questions']} questions, {diff['clusters']} clusters\n  {cells}\n  {verdict(diff)}"


def settings(
    gold_path: Path, split: str, chunking_run: str, search: str = "dense", keyword_weight: float = 1.0
) -> dict:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True).stdout)
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, None
    return {
        "date": datetime.now(UTC).isoformat(timespec="seconds"), "git_commit": commit, "uncommitted_changes": dirty,
        "split": split,
        "gold_sha256": hashlib.sha256(gold_path.read_bytes()).hexdigest(), "chunking_run": chunking_run,
        "embedding_model": MODEL, "search": SEARCH_TEXT[search], "keyword_weight": keyword_weight if search == "hybrid" else None,
        "language_filter": True,
        "unit": "article (best chunk), top 20", "ndcg_gain": "linear (the grade)",
        "bootstrap": "2000 resamples of clusters, 95% percentile interval",
    }


def by(rows: list[dict], key: str) -> dict[str, list[dict]]:
    grouped = defaultdict(list)
    for r in rows:
        grouped[r[key]].append(r)
    return dict(sorted(grouped.items()))
