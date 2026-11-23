import pytest

pytest.importorskip("fastapi")

from pydantic import ValidationError

from legalrag.web import schemas


def test_a_reply_refuses_a_misspelled_field_instead_of_leaving_the_default():
    with pytest.raises(ValidationError, match="Extra inputs"):
        schemas.AskReply(request_id="a", outcome="rate_limited", reson="more than 5 questions a minute")
    with pytest.raises(ValidationError, match="Extra inputs"):
        schemas.HealthReply(status="ok", llm_enabled=True, cache_warmed="done")


def test_a_reply_without_a_required_field_is_refused():
    with pytest.raises(ValidationError, match="request_id"):
        schemas.AskReply(outcome="answered")


def test_a_request_ignores_a_field_it_does_not_know_so_that_the_page_can_add_one_later():
    assert schemas.AskRequest(question="Quelle durée ?", page_version="2").question == "Quelle durée ?"
