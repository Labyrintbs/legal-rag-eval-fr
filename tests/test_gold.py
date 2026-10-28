import pytest
from pydantic import ValidationError

from legalrag import gold


def article(label="L1237-1", grade=2, lang="fr", source="code_travail", content_hash="h1"):
    return gold.GoldArticle(source=source, article=label, lang=lang, grade=grade, content_hash=content_hash)


def question(qid="q1", kind="answerable", articles=None):
    return gold.GoldQuestion(
        id=qid, question="Quel est le préavis ?", lang="fr", group="A", kind=kind,
        gold=[article()] if articles is None else articles, provenance=gold.Provenance(method="hand_written"),
    )


def test_a_question_needs_a_primary_article_unless_it_is_unanswerable():
    with pytest.raises(ValidationError, match="primary"):
        question(articles=[article(grade=1)])
    with pytest.raises(ValidationError, match="primary"):
        question(articles=[])
    assert question(kind="unanswerable", articles=[]).gold == []


def test_an_unanswerable_question_has_no_gold():
    with pytest.raises(ValidationError, match="no gold"):
        question(kind="unanswerable")


def test_the_same_article_cannot_be_listed_twice():
    with pytest.raises(ValidationError, match="twice"):
        question(articles=[article(), article(grade=1)])


def test_grades_other_than_1_and_2_are_refused():
    with pytest.raises(ValidationError):
        article(grade=3)


def test_gold_file_round_trip_and_duplicate_ids(tmp_path):
    path = tmp_path / "gold.jsonl"
    questions = [question("q1"), question("q2", kind="unanswerable", articles=[])]
    gold.write_gold(path, questions)
    assert gold.load_gold(path) == questions
    gold.write_gold(path, [question("q1"), question("q1")])
    with pytest.raises(ValueError, match="duplicate"):
        gold.load_gold(path)


def test_qrels_list_every_gold_article_with_its_grade_and_skip_unanswerable():
    questions = [
        question("q1", articles=[article("L1237-1"), article("L1237-2", grade=1)]),
        question("q2", kind="unanswerable", articles=[]),
    ]
    assert gold.to_qrels(questions) == [("q1", "L1237-1", 2), ("q1", "L1237-2", 1)]


def test_trec_lines_replace_spaces_in_labels():
    lines = gold.format_qrels([("q1", "art 17", 2)])
    assert lines == "q1 0 art_17 2\n"


def test_hash_check_reports_missing_changed_and_ambiguous_articles():
    questions = [
        question("ok", articles=[article("A1", content_hash="h")]),
        question("missing", articles=[article("A2")]),
        question("changed", articles=[article("A3", content_hash="old")]),
        question("twice", articles=[article("A4", content_hash="h")]),
    ]
    hashes = {
        ("code_travail", "A1", "fr"): {"h"},
        ("code_travail", "A3", "fr"): {"new"},
        ("code_travail", "A4", "fr"): {"h", "other"},
    }
    problems = gold.check_hashes(questions, hashes)
    assert len(problems) == 3
    assert "missing: code_travail A2 (fr) is not in the database" in problems
    assert any(p.startswith("changed:") and "changed since" in p for p in problems)
    assert any(p.startswith("twice:") and "2 different" in p for p in problems)
