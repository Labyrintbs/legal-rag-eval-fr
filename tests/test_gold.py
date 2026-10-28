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


def test_sheet_provenance_records_who_chose_the_gold():
    p = gold.Provenance(method="ministry_sheet", source_heading="Comment ?", gold_origin="assistant")
    assert p.gold_origin == "assistant"
    with pytest.raises(ValidationError):
        gold.Provenance(method="ministry_sheet", gold_origin="somebody")


def split_question(qid, group, articles):
    gold_articles = [article(label, grade, content_hash=hash_) for label, grade, hash_ in articles]
    return gold.GoldQuestion(
        id=qid, question="q", lang="fr", group=group, kind="answerable" if gold_articles else "unanswerable",
        gold=gold_articles, provenance=gold.Provenance(method="hand_written"),
    )


def test_questions_sharing_a_primary_article_or_an_identical_body_stay_in_one_half():
    questions = [
        split_question("a", "A", [("X", 2, "h1")]),
        split_question("b", "B", [("X", 2, "h1")]),
        split_question("c", "A", [("Y", 2, "h1")]),  # a twin of X with the same body
        split_question("d", "A", [("Z", 1, "h1"), ("W", 2, "h9")]),  # grade 1 does not link
    ]
    split = gold.assign_split(questions)
    assert split["a"] == split["b"] == split["c"]
    assert set(split) == {"a", "b", "c", "d"}


def test_the_split_is_balanced_inside_each_group_and_is_repeatable():
    questions = [split_question(f"q{i}", "A" if i < 10 else "B", [(f"L{i}", 2, f"h{i}")]) for i in range(20)]
    split = gold.assign_split(questions)
    assert split == gold.assign_split(list(reversed(questions)))
    for group, ids in (("A", range(10)), ("B", range(10, 20))):
        halves = [split[f"q{i}"] for i in ids]
        assert abs(halves.count("dev") - halves.count("test")) <= 1, group
    assert abs(list(split.values()).count("dev") - list(split.values()).count("test")) <= 1


def test_unanswerable_questions_are_split_too_and_counted():
    questions = [split_question(f"u{i}", "G", []) for i in range(4)]
    for q in questions:
        q.split = gold.assign_split(questions)[q.id]
    assert gold.split_counts(questions) == {"G": {"dev": 2, "test": 2}}


def test_the_committed_gold_file_is_valid_and_split_in_two_halves():
    from pathlib import Path

    questions = gold.load_gold(Path(__file__).parent.parent / "eval" / "gold.jsonl")
    assert all(q.split in ("dev", "test") for q in questions)
    assert gold.assign_split(questions) == {q.id: q.split for q in questions}
    halves = [q.split for q in questions]
    assert abs(halves.count("dev") - halves.count("test")) <= 5
