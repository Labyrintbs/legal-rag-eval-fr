import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from legalrag import cli, evaluate, gold

runner = CliRunner()


def question(qid, group, articles, split="dev", kind="answerable"):
    items = [gold.GoldArticle(source="code_travail", article=a, lang="fr", grade=g, content_hash=h)
             for a, g, h in articles]
    return gold.GoldQuestion(id=qid, question="q", lang="fr", group=group, kind=kind, gold=items, split=split,
                             provenance=gold.Provenance(method="hand_written"))


def test_chunks_are_merged_to_articles_in_the_order_of_their_best_chunk():
    rows = [("code_travail", "article", "L1", "h1"), ("code_travail", "article", "L1", "h1"),
            ("rgpd", "article", "17", "h17"), ("rgpd", "recital", "65", "h65"), ("code_travail", "article", "L2", "h2")]
    assert evaluate.merge_chunks(rows) == [("L1", "h1"), ("art 17", "h17"), ("rct 65", "h65"), ("L2", "h2")]
    assert evaluate.merge_chunks(rows, keep=2) == [("L1", "h1"), ("art 17", "h17")]


def test_scores_come_from_the_gold_and_unanswerable_questions_are_left_out_of_the_means():
    questions = [
        question("a", "A", [("L1", 2, "h1")]),
        question("b", "A", [("L2", 2, "h2")]),
        question("u", "G", [], kind="unanswerable"),
    ]
    retrieved = {"a": [("L1", "h1")], "b": [("L9", "x"), ("L2", "h2")], "u": [("L9", "x")]}
    rows = evaluate.score(questions, retrieved)
    assert rows[0]["metrics"]["mrr@10"] == 1.0 and rows[1]["metrics"]["mrr@10"] == 0.5
    assert rows[2]["metrics"] is None and rows[2]["ranked"] == ["L9"]
    summary = evaluate.summarize(rows)
    assert summary["questions"] == 2
    assert summary["metrics"]["mrr@10"][0] == pytest.approx(0.75)
    assert evaluate.summarize(rows, lambda r: r["group"] == "G") is None
    assert "no question with gold" in evaluate.format_summary("G", None)


def test_questions_on_the_same_article_are_one_cluster_in_the_summary():
    questions = [question("a", "A", [("L1", 2, "h1")]), question("b", "B", [("L1", 2, "h1")]),
                 question("c", "A", [("L2", 2, "h2")])]
    rows = evaluate.score(questions, {q.id: [("L1", "h1")] for q in questions})
    assert evaluate.summarize(rows)["clusters"] == 2


def test_the_test_half_needs_the_final_flag(tmp_path):
    result = runner.invoke(cli.app, ["eval", "--split", "test"])
    assert result.exit_code != 0 and "--final" in result.output
    assert runner.invoke(cli.app, ["eval", "--split", "other"]).exit_code != 0


def test_settings_record_the_gold_file_and_the_search(tmp_path):
    path = tmp_path / "gold.jsonl"
    path.write_text(json.dumps({"id": "x"}))
    s = evaluate.settings(path, "dev", "default")
    assert len(s["gold_sha256"]) == 64 and s["search"].startswith("dense, exact") and s["language_filter"]
    assert evaluate.settings(path, "dev", "default", "hybrid")["search"].startswith("dense + keyword")


def test_reciprocal_rank_fusion_rewards_articles_found_by_both_searches():
    dense = [("A", "ha"), ("B", "hb"), ("C", "hc")]
    words = [("B", "hb"), ("D", "hd")]
    assert evaluate.fuse([dense, words]) == [("B", "hb"), ("A", "ha"), ("D", "hd"), ("C", "hc")]
    assert evaluate.fuse([dense, words], keep=2) == [("B", "hb"), ("A", "ha")]


def test_fusion_ties_keep_the_order_of_the_lists():
    assert evaluate.fuse([[("X", "hx")], [("Y", "hy")]]) == [("X", "hx"), ("Y", "hy")]


def test_a_small_weight_lets_the_first_list_dominate_the_fusion():
    dense, words = [("A", "ha"), ("B", "hb")], [("B", "hb")]
    assert evaluate.fuse([dense, words])[0][0] == "B"
    assert evaluate.fuse([dense, words], weights=[1.0, 0.01])[0][0] == "A"
    assert evaluate.settings(Path(__file__), "dev", "default", "hybrid", 0.5)["keyword_weight"] == 0.5


def test_every_search_asks_for_the_depth_it_needs(monkeypatch):
    calls = []
    monkeypatch.setattr(evaluate, "retrieve", lambda conn, run, lang, v, keep, model: calls.append(("dense", keep)) or [("A", "ha")])
    monkeypatch.setattr(evaluate.keyword.Bm25Index, "build", classmethod(lambda cls, conn, run, lang: "index"))
    monkeypatch.setattr(evaluate, "retrieve_keyword",
                        lambda conn, index, lang, text, keep: calls.append(("keyword", keep)) or [("B", "hb")])
    questions = [question("a", "A", [("A", 2, "ha")])]
    assert evaluate.retrieve_all(None, 1, questions, [None], "dense") == {"a": [("A", "ha")]}
    assert evaluate.retrieve_all(None, 1, questions, None, "keyword") == {"a": [("B", "hb")]}
    assert evaluate.retrieve_all(None, 1, questions, [None], "hybrid") == {"a": [("A", "ha"), ("B", "hb")]}
    assert calls == [("dense", 20), ("keyword", 20), ("dense", 100), ("keyword", 100)]


def run_file(rows, gold_sha="g", split="dev"):
    return {"settings": {"gold_sha256": gold_sha, "split": split},
            "rows": [{"id": i, "cluster": c, "group": "A", "metrics": m} for i, c, m in rows]}


def metric_dict(ndcg, recall):
    return {name: (ndcg if name.startswith("ndcg") else recall) for name in evaluate.metrics.METRICS}


def test_compare_gives_the_paired_difference_and_the_verdict():
    base = run_file([(f"q{i}", f"c{i}", metric_dict(0.5, 0.5)) for i in range(20)])
    better = run_file([(f"q{i}", f"c{i}", metric_dict(0.7, 0.5)) for i in range(20)])
    diff = evaluate.compare(base, better)
    assert diff["questions"] == 20 and diff["metrics"]["ndcg@10"][0] == pytest.approx(0.2)
    assert evaluate.verdict(diff).endswith("improvement by decision 3b")
    worse_recall = run_file([(f"q{i}", f"c{i}", metric_dict(0.7, 0.3)) for i in range(20)])
    assert "Recall@10 clearly down: not an improvement" in evaluate.verdict(evaluate.compare(base, worse_recall))
    assert "nDCG@10 not clearly changed" in evaluate.verdict(evaluate.compare(base, base))


def test_compare_refuses_runs_that_are_not_comparable():
    base = run_file([("q1", "c1", metric_dict(0.5, 0.5))])
    with pytest.raises(ValueError, match="gold_sha256"):
        evaluate.compare(base, run_file([("q1", "c1", metric_dict(0.5, 0.5))], gold_sha="other"))
    with pytest.raises(ValueError, match="split"):
        evaluate.compare(base, run_file([("q1", "c1", metric_dict(0.5, 0.5))], split="test"))
    with pytest.raises(ValueError, match="same questions"):
        evaluate.compare(base, run_file([("q2", "c2", metric_dict(0.5, 0.5))]))


def test_unknown_search_and_missing_run_file_are_refused():
    assert runner.invoke(cli.app, ["eval", "--search", "fuzzy"]).exit_code != 0
    result = runner.invoke(cli.app, ["compare", "nothing", "nowhere"])
    assert result.exit_code != 0 and "no run file" in result.output
