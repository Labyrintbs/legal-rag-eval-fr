import math

import pytest

from legalrag import keyword


def row(chunk, num, lexeme, tf=1):
    return (chunk, "code_travail", "article", num, f"h{chunk}", lexeme, tf)


def test_score_follows_the_bm25_formula():
    index = keyword.Bm25Index([row(1, "L1", "x"), row(1, "L1", "y"), row(2, "L2", "y")])
    # 2 chunks, x in 1 of them; chunk lengths 2 and 1 (average 1.5); k1 1.2, b 0.75
    idf = math.log(1 + (2 - 1 + 0.5) / (1 + 0.5))
    assert index.scores(["x"]) == {1: pytest.approx(idf * 2.2 / (1 + 1.2 * 1.25))}
    assert index.search(["x"], 10) == [("code_travail", "article", "L1", "h1")]


def test_a_rare_word_outweighs_a_common_one():
    rows = [row(1, "L1", "contrat"), row(1, "L1", "licenci"), row(2, "L2", "contrat"), row(3, "L3", "contrat")]
    index = keyword.Bm25Index(rows)
    assert index.search(["contrat", "licenci"], 3)[0][2] == "L1"


def test_repeated_word_counts_more_and_unknown_word_is_ignored():
    index = keyword.Bm25Index([row(1, "L1", "greve", 3), row(1, "L1", "autre"), row(2, "L2", "greve"),
                               row(2, "L2", "autre", 2)])
    assert [r[2] for r in index.search(["greve", "inconnu"], 5)] == ["L1", "L2"]
    assert index.search(["inconnu"], 5) == []


def test_ties_keep_the_chunk_order_and_top_limits_the_list():
    index = keyword.Bm25Index([row(2, "L2", "a"), row(1, "L1", "a"), row(3, "L3", "a")])
    assert [r[2] for r in index.search(["a"], 2)] == ["L1", "L2"]
