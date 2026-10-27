from pathlib import Path

import numpy as np
import pytest

from legalrag.smoke import (
    Hit,
    Question,
    article_label,
    embed_questions,
    first_hit_rank,
    format_result,
    load_questions,
)

QUESTIONS = Path(__file__).parent / "smoke_questions.yaml"


class StubEmbedder:
    """Returns a fixed, deliberately not normalised vector per call."""

    def encode(self, texts, batch_size):
        return np.array([[3.0, 4.0]] * len(texts), dtype=np.float32)

    def info(self):
        return {}


def hit(label, distance=0.2):
    return Hit(label, "fr", 0, 1, distance, "header", "first line\nsecond line")


def test_the_questions_file_is_well_formed():
    questions = load_questions(QUESTIONS)
    assert [q.id for q in questions] == list(range(1, len(questions) + 1))
    assert {q.group for q in questions} == set("ABCDEFG")
    assert all(q.question.strip() and q.lang in ("fr", "en") for q in questions)
    assert [q.id for q in questions if not q.expected] == [28, 29]


def test_duplicate_ids_are_refused(tmp_path):
    path = tmp_path / "q.yaml"
    path.write_text("- {id: 1, group: A, lang: fr, question: a}\n- {id: 1, group: A, lang: fr, question: b}\n")
    with pytest.raises(ValueError, match="duplicate"):
        load_questions(path)


def test_labels_follow_the_smoke_output_names():
    assert article_label("code_travail", "article", "L1237-1") == "L1237-1"
    assert article_label("code_travail", "annex", "Annexe III") == "Annexe III"
    assert article_label("rgpd", "article", "17") == "art 17"
    assert article_label("rgpd", "recital", "65") == "rct 65"


def test_question_vectors_have_unit_length():
    (v,) = embed_questions([Question(id=1, group="A", lang="fr", question="q")], StubEmbedder())
    assert v.tolist() == pytest.approx([0.6, 0.8])


def test_first_hit_rank_is_one_based_and_none_when_absent():
    hits = [hit("L1"), hit("L2"), hit("L3")]
    assert first_hit_rank(hits, ["L3", "L2"]) == 2
    assert first_hit_rank(hits, ["L9"]) is None
    assert first_hit_rank(hits, []) is None


def test_result_marks_expected_articles_and_says_where_the_first_one_is():
    q = Question(id=7, group="B", lang="fr", question="Quoi ?", expected=["L2"])
    out = format_result(q, [hit("L1"), hit("L2")])
    assert "rank 2" in out
    assert "  2* " in out and "  1  " in out
    assert "first line second line" in out
    unanswerable = format_result(Question(id=8, group="G", lang="fr", question="x"), [hit("L1")])
    assert "no expected article" in unanswerable
    missed = format_result(q, [hit("L1")])
    assert "NOT in the top" in missed
