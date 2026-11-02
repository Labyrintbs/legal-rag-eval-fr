from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from legalrag import evaluate, gold, keyword, sparse
from legalrag.cli import app
from legalrag.embed import embed_text_hash

runner = CliRunner()


def test_pool_keeps_the_largest_positive_weight_per_token_and_drops_special_tokens():
    ids, weights = sparse.pool([0, 5, 7, 5, 2, 9, 7], [0.9, 0.2, 0.5, 0.4, 0.3, 0.0, 0.1], {0, 2})
    assert ids == [5, 7] and weights == pytest.approx([0.4, 0.5])


def chunk_rows():
    """(article uid, chunk index, lang, text, source, kind, number, content hash) for three French chunks."""
    return [("a", 0, "fr", "text a", "code_travail", "article", "L1", "ha"),
            ("b", 0, "fr", "text b", "code_travail", "article", "L2", "hb"),
            ("c", 0, "en", "text c", "rgpd", "article", "17", "hc")]


def frame(overrides=None):
    vectors = {"a": ([1, 2], [1.0, 0.5]), "b": ([2, 3], [2.0, 1.0]), "c": ([1], [1.0])} | (overrides or {})
    return pd.DataFrame({
        "article_uid": list(vectors), "chunk_index": 0,
        "text_hash": [embed_text_hash(f"text {u}") for u in vectors],
        "token_ids": [np.asarray(v[0], dtype=np.int32) for v in vectors.values()],
        "weights": [np.asarray(v[1], dtype=np.float32) for v in vectors.values()],
    })


def test_the_index_scores_shared_tokens_by_the_product_of_weights_and_filters_by_language():
    index = sparse.SparseIndex(frame(), chunk_rows())
    assert index.scores(([2], [1.0]), "fr").tolist() == [0.5, 2.0]
    assert index.search(([2, 3], [1.0, 1.0]), "fr") == [("code_travail", "article", "L2", "hb"),
                                                         ("code_travail", "article", "L1", "ha")]
    assert index.search(([1], [1.0]), "en") == [("rgpd", "article", "17", "hc")]
    assert index.search(([99], [1.0]), "fr") == []  # no shared token, no result


def test_the_index_refuses_a_file_that_does_not_fit_the_run():
    with pytest.raises(ValueError, match="differ"):
        sparse.SparseIndex(frame().iloc[:2], chunk_rows())
    changed = chunk_rows()
    changed[0] = ("a", 0, "fr", "other text", "code_travail", "article", "L1", "ha")
    with pytest.raises(ValueError, match="another text"):
        sparse.SparseIndex(frame(), changed)


def test_the_sparse_file_round_trips(tmp_path):
    from legalrag.models import Chunk
    chunk = Chunk(article_uid="a", chunk_index=0, lang="fr", header_text="", body_text="text a", embed_text="text a", token_count=2)
    sparse.write(tmp_path / "s.parquet", [chunk], [([4, 8], [0.5, 1.5])])
    row = pd.read_parquet(tmp_path / "s.parquet").iloc[0]
    assert row.text_hash == embed_text_hash("text a") and list(row.token_ids) == [4, 8] and list(row.weights) == [0.5, 1.5]


def test_the_ts_rank_query_is_an_or_of_quoted_lexemes_without_repeats():
    assert keyword.tsrank_query(["travail", "préavis", "travail"]) == "'travail' | 'préavis'"
    assert keyword.tsrank_query(["l'a"]) == "'l''a'"
    assert keyword.TSRANK_NORMALIZATION == {"tsrank": 0, "tsrank-len": 1}


def question():
    return gold.GoldQuestion(id="a", question="q", lang="fr", group="A", kind="answerable",
                             gold=[gold.GoldArticle(source="code_travail", article="L1", lang="fr", grade=2, content_hash="ha")],
                             split="dev", provenance=gold.Provenance(method="hand_written"))


def test_the_lexical_choice_picks_the_word_matching_search(monkeypatch):
    seen = []
    monkeypatch.setattr(keyword, "search_tsrank", lambda conn, run, lang, text, method, top: seen.append(method) or [("code_travail", "article", "L1", "ha")])
    monkeypatch.setattr(keyword, "query_lexemes", lambda *a: ["x"])
    q = question()
    assert evaluate.retrieve_lexical(None, 1, q, "tsrank-len", {}, None, None, 5) == [("L1", "ha")] and seen == ["tsrank-len"]
    index = sparse.SparseIndex(frame(), chunk_rows())
    assert evaluate.retrieve_lexical(None, 1, q, "sparse", {}, index, ([2], [1.0]), 5) == [("L2", "hb"), ("L1", "ha")]


def test_lexical_must_be_a_known_method_and_is_recorded():
    result = runner.invoke(app, ["eval", "--search", "keyword", "--lexical", "other"])
    assert result.exit_code != 0 and "lexical must be" in result.output
    s = evaluate.settings(Path(__file__), "dev", "default", "hybrid", lexical="tsrank", sparse={"k": 1})
    assert s["lexical"] == "tsrank" and s["sparse"] == {"k": 1}
    assert evaluate.settings(Path(__file__), "dev", "default")["lexical"] is None

