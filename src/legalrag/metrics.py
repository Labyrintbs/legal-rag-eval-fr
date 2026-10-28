"""Retrieval metrics on article rankings (decisions 3 and 4).

A ranking is a list of articles, chunks already merged. Grades are 2 (primary) and 1 (acceptable);
nDCG uses the grade as the gain (the trec_eval and ir_measures default), so the cross-check in the
tests compares like with like.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

PRIMARY = 2
RECALL_KS = (5, 10, 20)
METRICS = ("hit@5", "recall@5", "recall@10", "recall@20", "mrr@10", "ndcg@5", "ndcg@10")


@dataclass
class Matched:
    gains: list[int]  # grade of each ranked article, 0 when it is not gold
    ideal: list[int]  # grades of all gold articles


def match_ranking(ranked: Sequence[tuple[str, str]], gold: Sequence[tuple[str, str, int]]) -> Matched:
    """ranked: (label, content hash) in rank order; gold: (label, content hash, grade).

    An article with the same body as a gold article counts as that gold article (decision 2). Each
    gold article is matched once; a later article with the same body as an already matched one is
    left out of the ranking, so the duplicate does not take a rank.
    """
    open_items = list(gold)
    gains = []
    for label, body_hash in ranked:
        item = next((g for g in open_items if g[0] == label), None) \
            or next((g for g in open_items if g[1] == body_hash), None)
        if item is not None:
            open_items.remove(item)
            gains.append(item[2])
        elif not any(g[1] == body_hash for g in gold):
            gains.append(0)
    return Matched(gains, [g[2] for g in gold])


def _dcg(gains: Sequence[int]) -> float:
    return sum(g / math.log2(rank + 2) for rank, g in enumerate(gains))


def recall_at(m: Matched, k: int) -> float:
    return sum(g > 0 for g in m.gains[:k]) / len(m.ideal)


def hit_at(m: Matched, k: int) -> float:
    return float(any(g > 0 for g in m.gains[:k]))


def mrr_at(m: Matched, k: int) -> float:
    """Reciprocal rank of the first primary article."""
    for rank, g in enumerate(m.gains[:k], 1):
        if g == PRIMARY:
            return 1 / rank
    return 0.0


def ndcg_at(m: Matched, k: int) -> float:
    return _dcg(m.gains[:k]) / _dcg(sorted(m.ideal, reverse=True)[:k])


def question_metrics(m: Matched) -> dict[str, float]:
    return {
        "hit@5": hit_at(m, 5),
        **{f"recall@{k}": recall_at(m, k) for k in RECALL_KS},
        "mrr@10": mrr_at(m, 10),
        "ndcg@5": ndcg_at(m, 5),
        "ndcg@10": ndcg_at(m, 10),
    }


def _cluster_sums(values: Sequence[float], clusters: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for v, c in zip(values, clusters, strict=True):
        sums[c] = sums.get(c, 0.0) + v
        counts[c] = counts.get(c, 0) + 1
    names = sorted(sums)
    return np.array([sums[n] for n in names]), np.array([counts[n] for n in names])


def bootstrap_ci(
    values: Sequence[float], clusters: Sequence[str], n: int = 2000, seed: int = 0, level: float = 0.95
) -> tuple[float, float, float]:
    """(mean, low, high). Whole clusters are resampled, not single questions: questions on the same
    article are not independent (decision 8)."""
    sums, counts = _cluster_sums(values, clusters)
    picks = np.random.default_rng(seed).integers(0, len(sums), (n, len(sums)))
    means = sums[picks].sum(axis=1) / counts[picks].sum(axis=1)
    tail = (1 - level) / 2 * 100
    return float(sums.sum() / counts.sum()), float(np.percentile(means, tail)), float(np.percentile(means, 100 - tail))


def bootstrap_diff(
    a: Sequence[float], b: Sequence[float], clusters: Sequence[str], n: int = 2000, seed: int = 0,
    level: float = 0.95,
) -> tuple[float, float, float]:
    """Mean of b minus a with its interval, on the same questions and the same resampled clusters
    (paired), for comparing two runs (decision 3b)."""
    return bootstrap_ci([y - x for x, y in zip(a, b, strict=True)], clusters, n, seed, level)
