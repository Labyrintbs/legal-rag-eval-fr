from pathlib import Path

import pytest

from legalrag.answering import articlenum
from legalrag.evaluation import evaluate, gold


class FakeConn:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def execute(self, sql, params):
        self.calls.append(params)
        return self

    def fetchall(self):
        return self.rows


@pytest.mark.parametrize("text, expected", [
    ("Que dit l'article L1221-13 du code du travail ?", [("code_travail", "article", "L1221-13")]),
    ("Et l'art. R*3231-4 ?", [("code_travail", "article", "R*3231-4")]),
    ("Entre D1234-5 et L1234-5-1, lequel s'applique ?",
     [("code_travail", "article", "D1234-5"), ("code_travail", "article", "L1234-5-1")]),
    ("Que dit l'article 17 du RGPD ?", [("rgpd", "article", "17")]),
    ("What does article 17 of the GDPR say?", [("rgpd", "article", "17")]),
    ("Que dit le considérant 42 ?", [("rgpd", "recital", "42")]),
    ("Que dit l'article 17 ?", []),  # a bare number may be any text
    ("Quelle est la durée du préavis ?", []),
    ("La loi 2008-596 du 25 juin 2008", []),
    ("L1221-13 et L1221-13 encore", [("code_travail", "article", "L1221-13")]),
])
def test_named_articles(text, expected):
    assert articlenum.named_articles(text) == expected


def test_lookup_keeps_only_the_articles_that_exist_and_asks_in_the_question_language():
    conn = FakeConn([("code_travail", "article", "L1221-13", "h1")])
    found = articlenum.lookup(conn, "Entre L1221-13 et L9999-99, lequel ?", "fr")
    assert found == [("L1221-13", "h1")]
    assert conn.calls[0][0] == "fr"


def test_lookup_without_a_number_does_not_touch_the_database():
    conn = FakeConn([])
    assert articlenum.lookup(conn, "Quelle est la durée du préavis ?", "fr") == []
    assert conn.calls == []


def test_lookup_labels_gdpr_articles_like_the_rankings():
    conn = FakeConn([("rgpd", "article", "17", "h")])
    assert articlenum.lookup(conn, "article 17 du RGPD", "en") == [("art 17", "h")]


def test_put_first_moves_a_named_article_up_without_repeating_it():
    ranking = [("A", "ha"), ("B", "hb"), ("C", "hc")]
    assert articlenum.put_first([("C", "hc")], ranking, 3) == [("C", "hc"), ("A", "ha"), ("B", "hb")]
    assert articlenum.put_first([("Z", "hz")], ranking, 3) == [("Z", "hz"), ("A", "ha"), ("B", "hb")]
    assert articlenum.put_first([], ranking, 2) == [("A", "ha"), ("B", "hb")]


def test_the_evaluation_applies_the_rule_only_when_asked(monkeypatch):
    monkeypatch.setattr(evaluate, "retrieve", lambda conn, run, lang, v, keep, model: [("A", "ha")])
    conn = FakeConn([("code_travail", "article", "L1221-13", "h1")])
    q = gold.GoldQuestion(id="a", question="Que dit l'article L1221-13 ?", lang="fr", group="A", kind="answerable",
                          gold=[gold.GoldArticle(source="code_travail", article="L1221-13", lang="fr", grade=2,
                                                 content_hash="h1")],
                          split="dev", provenance=gold.Provenance(method="hand_written"))
    assert evaluate.retrieve_all(conn, 1, [q], [None], "dense") == {"a": [("A", "ha")]}
    assert evaluate.retrieve_all(conn, 1, [q], [None], "dense", article_lookup=True) == {
        "a": [("L1221-13", "h1"), ("A", "ha")]}
    assert evaluate.settings(Path(__file__), "dev", "default", article_lookup=True)["article_lookup"] is True
