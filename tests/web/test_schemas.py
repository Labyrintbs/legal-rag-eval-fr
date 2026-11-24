import pytest

pytest.importorskip("fastapi")

from pydantic import ValidationError

from legalrag.web import schemas


def test_a_reply_refuses_a_misspelled_field_instead_of_leaving_the_default():
    with pytest.raises(ValidationError, match="Extra inputs"):
        schemas.AskReply(request_id="a", outcome="rate_limited", reson="more than 5 questions a minute")
    with pytest.raises(ValidationError, match="Extra inputs"):
        schemas.HealthReply(status="ok", llm_enabled=True, cache_warmed="done")


def test_the_path_of_an_article_keeps_the_current_title_of_each_level():
    path = ("Partie législative > Troisième partie : Durée > Livre Ier : Durée du travail > Chapitre Ier : Durée du travail > "
            "Chapitre Ier : Durée et aménagement > Section 3 : Durées maximales > Section 3 : Durée légale > "
            "Sous-section 3 : Durées hebdomadaires maximales. > Sous-section 3 : Dispositions supplétives.")
    assert schemas.tidy_path(path) == ("Partie législative > Troisième partie : Durée > Livre Ier : Durée du travail > "
                                       "Chapitre Ier : Durée et aménagement > Section 3 : Durée légale > Sous-section 3 : Dispositions supplétives.")
    assert schemas.tidy_path("Annexe") == "Annexe"  # a level without a number is kept
    assert schemas.tidy_path("Chapitre Ier : A > Section 1 : B") == "Chapitre Ier : A > Section 1 : B"  # different levels stay
    assert schemas.tidy_path("") == ""


def test_the_citation_numbers_of_the_translation_are_those_the_page_gives():
    one, two = {"label": "L1", "units": [1], "x": 1}, {"label": "L1", "units": [2]}
    claims = [{"text": "A.", "citations": [one]}, {"text": "B.", "citations": [two, one]}, {"text": "C.", "citations": []},
              {"text": "D.", "citations": [{"label": "art 17", "units": [1, 2]}]}]
    # one number per distinct passage, in the order of the sentences: the same rule as the answer card of the page
    assert schemas.numbered_claims(claims) == ["A. [1]", "B. [2][1]", "C.", "D. [3]"]


def test_a_reply_without_a_required_field_is_refused():
    with pytest.raises(ValidationError, match="request_id"):
        schemas.AskReply(outcome="answered")


def test_a_request_ignores_a_field_it_does_not_know_so_that_the_page_can_add_one_later():
    assert schemas.AskRequest(question="Quelle durée ?", page_version="2").question == "Quelle durée ?"
