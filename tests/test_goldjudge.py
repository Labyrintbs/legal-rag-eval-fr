from legalrag import goldjudge as gj
from legalrag.gold import GoldArticle, GoldQuestion, Provenance


def question(articles, kind="answerable"):
    gold = [GoldArticle(source="code_travail", article=a, lang="fr", grade=g, content_hash="h") for a, g in articles]
    return GoldQuestion(id="q1", question="Quel préavis ?", lang="fr", group="A", kind=kind, gold=gold,
                        provenance=Provenance(method="hand_written"))


TEXTS = {"L1": ("ctx", "texte un"), "L2": ("ctx", "x" * 5000), "L3": ("ctx", "texte trois")}


def test_candidates_are_unique_shuffled_the_same_way_and_cut():
    a = gj.shuffled_candidates(["L1", "L2", "L1", "L3"], TEXTS, "q1")
    b = gj.shuffled_candidates(["L3", "L2", "L1"], TEXTS, "q1")
    assert [c.label for c in a] == [c.label for c in b]
    assert sorted(c.label for c in a) == ["L1", "L2", "L3"]
    assert [c.id for c in a] == ["A1", "A2", "A3"]
    assert all(len(c.text) <= gj.TEXT_CHARS for c in a)


def test_messages_hide_which_articles_are_gold():
    candidates = gj.shuffled_candidates(["L1", "L3"], TEXTS, "q1")
    prompts = {"judges": {"j": {"system": "Juge."}}}
    system, user = gj.judge_messages(prompts, "j", "Quel préavis ?", candidates)
    assert system["content"] == "Juge." and "Quel préavis ?" in user["content"]
    assert "texte un" in user["content"] and "gold" not in user["content"].lower()


def test_compare_reports_grade_differences_extra_articles_and_kind():
    candidates = gj.shuffled_candidates(["L1", "L2", "L3"], TEXTS, "q1")
    ids = {c.label: c.id for c in candidates}
    verdict = {
        "articles": [{"id": ids["L1"], "grade": 1}, {"id": ids["L2"], "grade": 0}, {"id": ids["L3"], "grade": 2}],
        "question": {"kind": "underspecified", "sure": True},
    }
    result = gj.compare(question([("L1", 2), ("L2", 1)]), verdict, candidates)
    assert result["grade_differences"] == {"L1": (2, 1), "L2": (1, 0)}
    assert result["missing_from_gold"] == {"L3": 2}
    assert result["kind"] == ("answerable", "underspecified") and not result["kind_agrees"]


def test_compare_marks_a_verdict_with_a_missing_grade_as_failed():
    candidates = gj.shuffled_candidates(["L1", "L2"], TEXTS, "q1")
    verdict = {"articles": [{"id": "A1", "grade": 2}], "question": {"kind": "answerable"}}
    assert gj.compare(question([("L1", 2)]), verdict, candidates) == {"id": "q1", "failed": True}
    assert gj.compare(question([("L1", 2)]), {"error": "x"}, candidates)["failed"]
