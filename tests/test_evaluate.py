import json

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
