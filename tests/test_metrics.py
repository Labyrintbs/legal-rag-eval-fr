import math
import random

import ir_measures
import pytest
from ir_measures import RR, Success, nDCG
from ir_measures import R as Recall

from legalrag import metrics as m


def matched(gains, ideal):
    return m.Matched(gains, ideal)


def test_recall_hit_and_mrr_by_hand():
    # Rank 1 acceptable, rank 7 primary; gold = one primary and two acceptable.
    x = matched([1, 0, 0, 0, 0, 0, 2, 0, 0, 0], [2, 1, 1])
    assert m.hit_at(x, 5) == 1.0
    assert m.recall_at(x, 5) == pytest.approx(1 / 3)
    assert m.recall_at(x, 10) == pytest.approx(2 / 3)
    assert m.mrr_at(x, 10) == pytest.approx(1 / 7)
    assert m.mrr_at(x, 5) == 0.0


def test_a_ranking_without_gold_scores_zero_everywhere():
    x = matched([0] * 10, [2, 1])
    assert set(m.question_metrics(x).values()) == {0.0}


def test_ndcg_with_grades_by_hand():
    # Gains by rank: 0, 2, 0, 1. Ideal order: 2, 1.
    x = matched([0, 2, 0, 1], [2, 1])
    dcg = 2 / math.log2(3) + 1 / math.log2(5)
    ideal = 2 / math.log2(2) + 1 / math.log2(3)
    assert m.ndcg_at(x, 5) == pytest.approx(dcg / ideal)
    assert m.ndcg_at(x, 5) == pytest.approx(0.6433, abs=1e-4)
    perfect = matched([2, 1, 0], [2, 1])
    assert m.ndcg_at(perfect, 10) == pytest.approx(1.0)


def test_ndcg_cuts_the_ideal_ranking_at_k():
    # Three gold articles, k = 2: the ideal is 2, 1 and the ranking found the 1 and the 2.
    x = matched([1, 2, 1], [2, 1, 1])
    assert m.ndcg_at(x, 2) == pytest.approx((1 + 2 / math.log2(3)) / (2 + 1 / math.log2(3)))


def test_an_article_with_the_same_body_counts_as_the_gold_article():
    gold = [("L1", "hash-1", 2)]
    ranking = [("L9", "other"), ("L2", "hash-1")]
    assert m.match_ranking(ranking, gold).gains == [0, 2]


def test_a_second_twin_of_a_matched_article_leaves_the_ranking():
    gold = [("L1", "hash-1", 2), ("L5", "hash-5", 1)]
    ranking = [("L1", "hash-1"), ("L2", "hash-1"), ("L7", "x"), ("L5", "hash-5")]
    matched_ranking = m.match_ranking(ranking, gold)
    assert matched_ranking.gains == [2, 0, 1]  # L2 dropped, so L5 is at rank 3
    assert matched_ranking.ideal == [2, 1]


def test_the_label_is_preferred_over_a_twin_with_the_same_body():
    gold = [("L1", "same", 2), ("L2", "same", 1)]
    assert m.match_ranking([("L2", "same")], gold).gains == [1]


def test_bootstrap_of_equal_values_has_no_spread_and_is_repeatable():
    values, clusters = [0.5] * 6, ["a", "a", "b", "c", "c", "d"]
    assert m.bootstrap_ci(values, clusters) == (0.5, 0.5, 0.5)
    mixed = [1, 0, 1, 1, 0, 0]
    first = m.bootstrap_ci(mixed, clusters, seed=3)
    assert first == m.bootstrap_ci(mixed, clusters, seed=3)
    mean, low, high = first
    assert mean == pytest.approx(0.5) and 0 <= low <= mean <= high <= 1


def test_the_bootstrap_resamples_clusters_so_a_single_cluster_has_no_interval():
    assert m.bootstrap_ci([1, 0, 1, 0], ["a"] * 4) == (0.5, 0.5, 0.5)


def test_paired_difference_is_zero_for_identical_runs_and_positive_for_a_better_one():
    base = [0.2, 0.4, 0.6, 0.8]
    clusters = ["a", "b", "c", "d"]
    assert m.bootstrap_diff(base, base, clusters) == (0.0, 0.0, 0.0)
    mean, low, high = m.bootstrap_diff(base, [x + 0.1 for x in base], clusters)
    assert mean == pytest.approx(0.1) and low == pytest.approx(0.1) and high == pytest.approx(0.1)


def test_our_metrics_agree_with_ir_measures_on_random_rankings():
    """Decision 4: one cross-check against the standard library (same linear gain for nDCG)."""
    rng = random.Random(7)
    qrels, run, ours = {}, {}, {}
    for q in range(40):
        docs = [f"d{i}" for i in range(30)]
        rng.shuffle(docs)
        grades = {d: rng.choice([1, 2]) for d in docs[: rng.randint(1, 4)]}
        grades[next(iter(grades))] = 2  # at least one primary, as in the gold file
        qrels[f"q{q}"] = grades
        ranking = docs[:25]
        run[f"q{q}"] = {d: -rank for rank, d in enumerate(ranking)}
        gains = m.match_ranking([(d, d) for d in ranking], [(d, d, g) for d, g in grades.items()])
        ours[f"q{q}"] = m.question_metrics(gains)
    measures = [Success(rel=1) @ 5, Recall(rel=1) @ 5, Recall(rel=1) @ 10, Recall(rel=1) @ 20,
                RR(rel=2) @ 10, nDCG @ 5, nDCG @ 10]
    names = dict(zip(measures, m.METRICS, strict=True))
    results = list(ir_measures.iter_calc(measures, qrels, run))
    assert len(results) == 40 * len(measures)
    for result in results:
        assert ours[result.query_id][names[result.measure]] == pytest.approx(result.value), (result.query_id, names[result.measure])
