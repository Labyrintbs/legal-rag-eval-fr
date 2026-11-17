import numpy as np
import pytest
from pydantic import ValidationError

from legalrag.evaluation import relevance


def unit(*values):
    v = np.array(values, dtype=float)
    return v / np.linalg.norm(v)


def test_the_verdict_accepts_the_three_labels_in_any_case_and_refuses_others():
    assert relevance.Verdict.model_validate_json('{"label": " Addresses "}').label == "addresses"
    with pytest.raises(ValidationError):
        relevance.Verdict.model_validate_json('{"label": "yes"}')


def test_the_generated_questions_must_not_be_empty():
    with pytest.raises(ValidationError):
        relevance.Generated.model_validate_json('{"questions": []}')


def test_pairs_give_each_answer_its_own_question_an_unrelated_one_and_the_nearest_one_about_other_articles():
    questions = {"a": "Qa", "b": "Qb", "c": "Qc", "d": "Qd"}
    vectors = {"a": unit(1, 0), "b": unit(1, 0.1), "c": unit(0, 1), "d": unit(1, 0.3)}
    gold = {"a": {"L1"}, "b": {"L1"}, "c": {"L2"}, "d": {"L3"}}  # b shares an article with a: never a wrong pair for it
    pairs = relevance.make_pairs({"a": "Ra"}, questions, vectors, gold, n=1, seed=1)
    assert [(p.key, p.question, p.answer) for p in pairs] == [("a|matched", "Qa", "Ra"), ("a|random", "Qc", "Ra"), ("a|near", "Qd", "Ra")]


def test_ragas_score_is_the_mean_cosine_and_separation_is_the_share_of_pairs_ordered_right():
    assert relevance.ragas_score(unit(1, 0), np.array([unit(1, 0), unit(0, 1)])) == pytest.approx(0.5)
    assert relevance.separation([0.9, 0.8], [0.3, 0.85]) == pytest.approx(0.75)
    assert relevance.separation([1, 1], [1, 1]) == 0.5
