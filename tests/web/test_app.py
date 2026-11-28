import json
import threading
import time
from functools import partial
from types import SimpleNamespace

import psycopg
import pytest
from conftest import with_database

pytest.importorskip("llama_index.core")
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, TextNode

from legalrag.answering import cache, limits, rag, trace
from legalrag.index import db
from legalrag.index.config import database_url
from legalrag.web import app as web
from legalrag.web import asking, build, schemas, warm

TRIAL = ("Le contrat de travail à durée indéterminée peut comporter une période d'essai dont la durée maximale est : "
         "1° Pour les ouvriers et les employés, de deux mois ; 2° Pour les agents de maîtrise et les techniciens, de trois mois ; "
         "3° Pour les cadres, de quatre mois.")
PROMPT = {"system": "Réponds en json.", "user": "Extraits :\n{context}\n\nQuestion : {question}\n"}
GOOD = json.dumps({"refusal": False, "claims": [{"text": "Quatre mois pour un cadre.", "sources": ["1.4"]}]})
REFUSAL = json.dumps({"refusal": True, "reason": "les extraits ne le disent pas", "claims": []})


def node(similarity=0.7, label="L1221-19"):
    return NodeWithScore(node=TextNode(id_=f"{label}#0", text=TRIAL, metadata={
        "label": label, "chunk_index": 0, "header": f"Code du travail, article {label}.", "section_path": "Titre II",
        "url": f"https://example/{label}"}), score=similarity)


class FakeRetriever(BaseRetriever):
    def __init__(self, nodes):
        super().__init__()
        self.nodes = nodes

    def _retrieve(self, query_bundle):
        return self.nodes


class FakeLLM:
    def __init__(self, reply=GOOD, error=None, served=None):
        self.reply, self.error, self.served, self.calls = reply, error, served, 0

    def chat(self, messages, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        usage = SimpleNamespace(prompt_tokens=1100, completion_tokens=90, prompt_cache_hit_tokens=1000)
        return SimpleNamespace(message=SimpleNamespace(content=self.reply), raw=SimpleNamespace(usage=usage, model=self.served))


class ScriptedLLM(FakeLLM):
    """Gives its replies one after the other (the translation first, then the answer)."""

    def __init__(self, *replies):
        super().__init__()
        self.replies = list(replies)

    def chat(self, messages, **kwargs):
        self.reply = self.replies.pop(0)
        return super().chat(messages, **kwargs)


TRANSLATE = {"system": "Traduis en français.", "user": "{question}\n", "max_tokens": 200}
TRANSLATE_ANSWER = {"system": "Translate into English.", "user": "{text}\n", "max_tokens": 700}
ENGLISH = "Four months for an executive (cadre). [1]"  # the translation of the one sentence of GOOD, with its citation number


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setenv("TRACE_SECRET", "test-secret")


@pytest.fixture
def url(database_name):
    return with_database(database_url(), database_name)


def engine_for(url, llm=None, nodes=None, gate=True, threshold=0.55, limit_settings=None):
    """An answer engine with a fake search and a fake model, over the throwaway database."""
    return rag.AnswerEngine(
        retriever=FakeRetriever(nodes if nodes is not None else [node(), node(0.65, "L1221-20")]),
        postprocessor=rag.NumberUnits(), llm=llm or FakeLLM(), prompt=PROMPT, model="deepseek-flash", prompt_id="answer.v3",
        threshold=threshold, gate=limits.Limits(lambda: db.connect(url), limit_settings) if gate else None,
        translate_prompt=TRANSLATE, translate_answer_prompt=TRANSLATE_ANSWER)


@pytest.fixture
def make(url, conn):
    """A client of the app over the throwaway database, with a fake search and a fake model."""

    def build_client(llm=None, nodes=None, settings=None, gate=True, threshold=0.55, warm=None, limit_settings=None):
        engine = engine_for(url, llm, nodes, gate, threshold, limit_settings)
        return TestClient(web.create_app(engine, lambda: db.connect(url), settings, warm))

    conn.execute("DELETE FROM query_traces")
    conn.execute("DELETE FROM answer_cache")  # cache rows are committed by the app: they would leak into the next test
    conn.execute("UPDATE service_flags SET value = true WHERE name = 'llm_enabled'")
    conn.commit()
    return build_client


def traced(conn, request_id):
    return conn.execute("SELECT mode, outcome, client_hash, question, answer FROM query_traces WHERE request_id = %s",
                        (request_id,)).fetchone()


def test_an_answer_has_claims_with_their_passages_the_articles_and_a_trace(make, conn):
    reply = make().post("/ask", json={"question": "Quelle durée pour un cadre ?"})
    body = reply.json()
    assert reply.status_code == 200 and body["outcome"] == "answered" and body["disclaimer"] == schemas.DISCLAIMER
    assert body["claims"][0]["text"] == "Quatre mois pour un cadre."
    assert body["claims"][0]["citations"][0]["label"] == "L1221-19"
    assert "quatre mois" in body["claims"][0]["citations"][0]["passage"]
    assert [a["label"] for a in body["articles"]] == ["L1221-19", "L1221-20"]
    mode, outcome, client, question, text = traced(conn, body["request_id"])
    assert (mode, outcome, question) == ("answer", "answered", "Quelle durée pour un cadre ?") and "Quatre mois" in text
    assert client is not None and "testclient" not in client  # the address is stored only as a hash


def test_a_weak_search_is_a_normal_reply_with_the_articles_and_no_model_call(make):
    llm = FakeLLM()
    reply = make(llm, nodes=[node(0.40)]).post("/ask", json={"question": "Quel est le SMIC ?"})
    assert reply.status_code == 200 and reply.json()["outcome"] == "refused_weak_retrieval"
    assert reply.json()["claims"] == [] and len(reply.json()["articles"]) == 1 and llm.calls == 0


def test_a_refusal_by_the_model_is_a_normal_reply(make):
    reply = make(FakeLLM(REFUSAL)).post("/ask", json={"question": "Que dit la loi sur X ?"})
    assert reply.status_code == 200 and reply.json()["outcome"] == "refused_by_model"
    assert reply.json()["reason"] == "les extraits ne le disent pas" and reply.json()["articles"]


def test_a_failed_model_is_a_502_with_the_articles(make):
    reply = make(FakeLLM(error=TimeoutError())).post("/ask", json={"question": "Quelle durée ?"})
    assert reply.status_code == 502 and reply.json()["outcome"] == "llm_error" and reply.json()["articles"]


def test_the_sixth_question_in_a_minute_gets_a_429_with_retry_after_and_the_articles(make):
    llm = FakeLLM()
    client = make(llm)
    for i in range(5):  # different questions: an identical one would come from the cache, without the model
        assert client.post("/ask", json={"question": f"Quelle durée {i} ?"}).status_code == 200
    reply = client.post("/ask", json={"question": "Quelle durée 5 ?"})
    assert reply.status_code == 429 and reply.json()["outcome"] == "rate_limited" and reply.json()["articles"]
    assert int(reply.headers["Retry-After"]) >= 1 and llm.calls == 5


def test_the_kill_switch_gives_a_503_and_search_still_works(make, conn):
    client = make()
    limits.set_llm_enabled(conn, False)
    reply = client.post("/ask", json={"question": "Quelle durée ?"})
    assert reply.status_code == 503 and reply.json()["outcome"] == "llm_disabled" and reply.json()["articles"]
    assert client.post("/search", json={"question": "Quelle durée ?"}).status_code == 200


def test_search_returns_the_articles_is_traced_in_search_mode_and_is_never_limited(make, conn):
    client = make()
    for _ in range(8):
        reply = client.post("/search", json={"question": "Quelle durée ?"})
        assert reply.status_code == 200
    body = reply.json()
    assert [a["label"] for a in body["articles"]] == ["L1221-19", "L1221-20"] and body["weak"] is False
    assert traced(conn, body["request_id"])[:2] == ("search", "answered") and traced(conn, body["request_id"])[4] is None
    assert make(nodes=[node(0.3)]).post("/search", json={"question": "SMIC ?"}).json()["weak"] is True


@pytest.mark.parametrize("question", ["", "   ", "x" * (schemas.MAX_QUESTION + 1)])
def test_an_empty_or_too_long_question_is_a_422_and_nothing_is_traced(make, conn, question):
    assert make().post("/ask", json={"question": question}).status_code == 422
    assert conn.execute("SELECT count(*) FROM query_traces").fetchone()[0] == 0


def test_only_french_is_accepted_for_now(make):
    assert make().post("/ask", json={"question": "Quelle durée ?", "lang": "en"}).status_code == 422


def test_feedback_is_stored_on_the_request_and_a_new_vote_replaces_it(make, conn):
    client = make()
    request_id = client.post("/ask", json={"question": "Quelle durée ?"}).json()["request_id"]
    vote = {"request_id": request_id, "value": -1, "kind": "wrong_citation", "comment": "  L1221-20 aurait suffi  "}
    assert client.post("/feedback", json=vote).json() == {"ok": True}
    row = conn.execute("SELECT feedback, feedback_kind, feedback_comment FROM query_traces WHERE request_id = %s", (request_id,)).fetchone()
    assert row == (-1, "wrong_citation", "L1221-20 aurait suffi")
    client.post("/feedback", json={"request_id": request_id, "value": 1})
    row = conn.execute("SELECT feedback, feedback_kind, feedback_comment FROM query_traces WHERE request_id = %s", (request_id,)).fetchone()
    assert row == (1, None, None)


def test_feedback_on_an_unknown_request_is_a_404(make):
    assert make().post("/feedback", json={"request_id": "unknown", "value": 1}).status_code == 404


@pytest.mark.parametrize("vote", [{"request_id": "a", "value": 0}, {"request_id": "a", "value": 1, "kind": "rude"},
                                  {"request_id": "a", "value": 1, "comment": "x" * (schemas.MAX_COMMENT + 1)}])
def test_a_bad_feedback_is_a_422(make, vote):
    assert make().post("/feedback", json=vote).status_code == 422


def test_feedback_is_limited_per_client(make):
    client = make(settings=web.Settings(feedback_per_minute=2))
    vote = {"request_id": "unknown", "value": 1}
    assert [client.post("/feedback", json=vote).status_code for _ in range(3)] == [404, 404, 429]


def test_the_client_is_read_from_the_proxy_header_only_when_one_is_named(make, conn):
    ask = {"question": "Quelle durée ?"}
    behind = make(settings=web.Settings(client_ip_header="x-forwarded-for"))
    # the last value is the one our proxy appended; a first value written by the visitor does not change who they are
    first = behind.post("/ask", json=ask, headers={"x-forwarded-for": "10.0.0.1, 203.0.113.7"}).json()["request_id"]
    again = behind.post("/ask", json=ask, headers={"x-forwarded-for": "203.0.113.7"}).json()["request_id"]
    forged = behind.post("/ask", json=ask, headers={"x-forwarded-for": "198.51.100.2, 203.0.113.7"}).json()["request_id"]
    other = behind.post("/ask", json=ask, headers={"x-forwarded-for": "198.51.100.2"}).json()["request_id"]
    assert traced(conn, first)[2] == traced(conn, again)[2] == traced(conn, forged)[2] != traced(conn, other)[2]
    direct = make().post("/ask", json=ask, headers={"x-forwarded-for": "203.0.113.7"}).json()["request_id"]
    assert traced(conn, direct)[2] != traced(conn, first)[2]  # without a named header the connection address counts


def test_a_failed_trace_write_does_not_break_the_answer(make, monkeypatch):
    client = make()
    monkeypatch.setattr(trace, "record", lambda conn, row: (_ for _ in ()).throw(RuntimeError("disk full")))
    assert client.post("/ask", json={"question": "Quelle durée ?"}).status_code == 200


def test_personal_identifiers_are_masked_before_the_engine_the_cache_and_the_trace_and_the_reply_says_so(make, conn):
    llm = FakeLLM()
    c = make(llm)
    asked = "Mon salarié (jean.dupont@example.com, 06 12 34 56 78) démissionne : quel préavis ?"
    body = c.post("/ask", json={"question": asked}).json()
    assert body["masked"] == ["email", "phone"] and body["question_masked"] == "Mon salarié ([e-mail], [téléphone]) démissionne : quel préavis ?"
    stored = traced(conn, body["request_id"])[3]
    assert stored == body["question_masked"] and "dupont" not in stored and "12 34" not in stored
    # a second question that differs only by the identifier shares the cached answer: the cache key holds the masked text
    other = c.post("/ask", json={"question": asked.replace("jean.dupont", "marie.martin")}).json()
    assert other["cached"] and llm.calls == 1
    assert c.post("/ask", json={"question": "Quelle durée pour un cadre ?"}).json()["masked"] == []


def test_a_search_and_a_comment_are_masked_too(make, conn):
    c = make()
    found = c.post("/search", json={"question": "Mon e-mail est a.b@c.fr : quelle durée de préavis ?"}).json()
    assert found["masked"] == ["email"] and "a.b@c.fr" not in traced(conn, found["request_id"])[3]
    answer = c.post("/ask", json={"question": "Quelle durée pour un directeur ?"}).json()
    c.post("/feedback", json={"request_id": answer["request_id"], "value": -1, "comment": "Écrivez-moi : x@y.fr"})
    assert conn.execute("SELECT feedback_comment FROM query_traces WHERE request_id = %s", (answer["request_id"],)).fetchone()[0] == "Écrivez-moi : [e-mail]"


FRENCH = "Quelle durée pour un cadre ?"


def cost_of(conn, request_id):
    return conn.execute("SELECT cost_usd FROM query_traces WHERE request_id = %s", (request_id,)).fetchone()[0]


def test_a_translated_question_is_answered_in_french_and_the_reply_and_the_trace_hold_the_french_question(make, conn):
    llm = ScriptedLLM(GOOD, FRENCH, GOOD)  # the plain answer, then the translation and the answer of the translated request
    c = make(llm)
    plain = c.post("/ask", json={"question": "Quelle durée pour un directeur ?"}).json()
    assert plain["question_fr"] is None  # no translation asked: nothing added
    body = c.post("/ask", json={"question": "How long for an executive?", "translate": True}).json()
    assert body["outcome"] == "answered" and body["question_fr"] == FRENCH and llm.calls == 3
    assert traced(conn, body["request_id"])[3] == FRENCH  # the question that was answered
    assert cost_of(conn, body["request_id"]) == pytest.approx(cost_of(conn, plain["request_id"]))  # the answer row holds the answer only
    count, cost = conn.execute("SELECT count(*), sum(cost_usd) FROM query_traces WHERE mode = 'translate'").fetchone()
    assert count == 1 and cost == pytest.approx(cost_of(conn, plain["request_id"]))  # the translation is traced apart, with its cost


def test_a_translated_question_shares_the_cache_with_the_same_french_question_and_still_pays_for_the_translation(make, conn):
    llm = ScriptedLLM(GOOD, FRENCH)
    c = make(llm)
    first = c.post("/ask", json={"question": FRENCH}).json()
    hit = c.post("/ask", json={"question": "How long for an executive?", "translate": True}).json()
    assert hit["cached"] and hit["question_fr"] == FRENCH and llm.calls == 2  # the answer call was not repeated
    assert traced(conn, hit["request_id"])[1] == "cache_hit" and not cost_of(conn, hit["request_id"])  # a stored reply costs nothing...
    assert conn.execute("SELECT count(*), sum(cost_usd) FROM query_traces WHERE mode = 'translate'").fetchone()[0] == 1  # ...but the translation did
    assert first["cached"] is False
    assert "question_fr" not in conn.execute("SELECT reply FROM answer_cache").fetchone()[0]  # stored without it


def test_a_translated_question_has_its_own_counters_and_is_refused_without_a_model_call_over_them(make):
    llm = ScriptedLLM(FRENCH, GOOD)
    c = make(llm, limit_settings=limits.Settings(translate_per_minute=1, translate_per_day=30, cost_per_day_usd=0.10))
    assert c.post("/ask", json={"question": "How long?", "translate": True}).status_code == 200
    reply = c.post("/ask", json={"question": "How long again?", "translate": True})
    assert reply.status_code == 429 and reply.json()["outcome"] == "rate_limited" and "Retry-After" in reply.headers
    assert llm.calls == 2  # the first translation and its answer: the second translation was not paid for


def test_a_translated_question_whose_answer_is_in_memory_still_uses_the_translation_counters(make, conn):
    """A translation call was made for each of these requests although every answer came from the memory: before, nothing counted them."""
    llm = ScriptedLLM(GOOD, *([FRENCH] * 8))
    c = make(llm, limit_settings=limits.Settings(translate_per_minute=3, translate_per_day=30, cost_per_day_usd=0.10))
    c.post("/ask", json={"question": FRENCH})  # now in memory
    codes = [c.post("/ask", json={"question": f"English question {i}?", "translate": True}).status_code for i in range(8)]
    assert codes == [200, 200, 200] + [429] * 5 and llm.calls == 1 + 3
    assert conn.execute("SELECT count(*) FROM query_traces WHERE mode = 'translate'").fetchone()[0] == 3


def test_a_translated_question_that_ends_in_a_weak_search_still_counts_its_translation(make, conn):
    llm = ScriptedLLM(*([FRENCH] * 6))
    c = make(llm, nodes=[node(0.40)], limit_settings=limits.Settings(translate_per_minute=2, translate_per_day=30, cost_per_day_usd=0.10))
    codes = [c.post("/ask", json={"question": f"English question {i}?", "translate": True}).status_code for i in range(4)]
    assert codes == [200, 200, 429, 429] and llm.calls == 2  # refused for a weak search: no answer, but the translation was paid


@pytest.mark.parametrize("llm", [FakeLLM(error=TimeoutError()), ScriptedLLM(""), ScriptedLLM("x" * 600)])
def test_a_failed_or_unusable_translation_is_a_502_and_no_answer_is_written(make, conn, llm):
    reply = make(llm).post("/ask", json={"question": "How long?", "translate": True})
    body = reply.json()
    assert reply.status_code == 502 and body["outcome"] == "llm_error" and "traduction" in body["reason"]
    assert llm.calls == 1
    # the call was made, so it counts as a translation (without a cost: the model's usage is not known) and no answer row exists
    assert conn.execute("SELECT outcome FROM query_traces WHERE mode = 'translate'").fetchall() == [("llm_error",)]
    assert conn.execute("SELECT count(*) FROM query_traces WHERE mode = 'answer'").fetchone()[0] == 0


def translate(client, answer):
    return client.post("/translate-answer", json={"request_id": answer["request_id"]})


def test_the_english_translation_of_an_answer_is_made_once_stored_with_the_answer_and_paid_in_one_trace(make, conn):
    llm = ScriptedLLM(GOOD, ENGLISH)
    c = make(llm)
    answer = c.post("/ask", json={"question": FRENCH}).json()
    first = translate(c, answer)
    assert first.status_code == 200
    assert first.json() == {"request_id": answer["request_id"], "english": ENGLISH, "stored": False}
    assert conn.execute("SELECT answer_en FROM answer_cache").fetchone()[0] == ENGLISH
    hit = c.post("/ask", json={"question": FRENCH}).json()  # the same answer, from memory, with a request of its own
    again = translate(c, hit)
    assert again.json()["stored"] is True and again.json()["english"] == ENGLISH
    assert llm.calls == 2  # one answer and one translation: the second translation was not paid for
    count, cost = conn.execute("SELECT count(*), sum(cost_usd) FROM query_traces WHERE mode = 'translate'").fetchone()
    assert count == 1 and cost > 0 and cost < 0.001
    row = conn.execute("SELECT question, outcome FROM query_traces WHERE mode = 'translate'").fetchone()
    assert row == ("", "answered")  # no text of any visitor


def test_a_translation_is_never_counted_as_an_answer_of_the_visitor(make):
    llm = ScriptedLLM(GOOD, ENGLISH)
    c = make(llm, limit_settings=limits.Settings(per_minute=1, per_day=30, cost_per_day_usd=0.10))
    answer = c.post("/ask", json={"question": FRENCH}).json()
    assert translate(c, answer).status_code == 200  # the one allowed answer of the minute is used, and the translation still works
    assert c.post("/ask", json={"question": "Quelle durée pour un directeur ?"}).status_code == 429


def test_only_an_answer_that_is_stored_can_be_translated(make, conn):
    c = make(FakeLLM(REFUSAL))
    refused = c.post("/ask", json={"question": FRENCH}).json()
    assert translate(c, refused).status_code == 404  # a refusal has nothing to translate
    assert translate(c, {"request_id": "unknown"}).status_code == 404
    c = make(ScriptedLLM(GOOD))
    answer = c.post("/ask", json={"question": "Quelle durée pour un directeur ?"}).json()
    conn.execute("UPDATE answer_cache SET expires_at = now() - interval '1 day'")
    conn.commit()
    assert translate(c, answer).status_code == 410


@pytest.mark.parametrize("bad", ["Four months. [2]", "Four months. [1]\nAnd more. [1]", "Four months for an executive.", ""])
def test_a_translation_that_loses_or_moves_a_citation_is_refused_and_not_stored(make, conn, bad):
    llm = ScriptedLLM(GOOD, bad)
    c = make(llm)
    answer = c.post("/ask", json={"question": FRENCH}).json()
    reply = translate(c, answer)
    assert reply.status_code == 502
    assert conn.execute("SELECT answer_en FROM answer_cache").fetchone()[0] is None
    assert conn.execute("SELECT count(*) FROM query_traces WHERE mode = 'translate'").fetchone()[0] == 0


def test_the_translation_has_its_own_limit_the_switch_and_the_budget(make, conn):
    llm = ScriptedLLM(GOOD, GOOD, GOOD, ENGLISH)  # three answers asked first, then the one translation that is allowed
    c = make(llm, limit_settings=limits.Settings(per_minute=9, per_day=30, translate_per_minute=1, cost_per_day_usd=0.10))
    first, second, third = (c.post("/ask", json={"question": f"Quelle durée pour un cadre n° {i} ?"}).json() for i in range(3))
    assert translate(c, first).status_code == 200
    limited = translate(c, second)
    assert limited.status_code == 429 and int(limited.headers["Retry-After"]) >= 1
    limits.set_llm_enabled(conn, False)
    assert translate(c, third).status_code == 503  # the switch stops a new translation
    assert translate(c, first).status_code == 200  # a stored one is still served


def test_health_says_whether_written_answers_are_on(make, conn):
    client = make()
    assert client.get("/health").json() == {
        "status": "ok", "llm_enabled": True, "cache_warm": "off", "llm_host": None, "llm_failing": False, "llm_other_model": None}
    limits.set_llm_enabled(conn, False)
    assert client.get("/health").json() == {
        "status": "ok", "llm_enabled": False, "cache_warm": "off", "llm_host": None, "llm_failing": False, "llm_other_model": None}


def test_health_names_the_model_provider_only_when_it_is_known(make):
    assert make(settings=asking.Settings(llm_host="api.example.eu")).get("/health").json() == {
        "status": "ok", "llm_enabled": True, "cache_warm": "off", "llm_host": "api.example.eu", "llm_failing": False,
        "llm_other_model": None}
    assert make().get("/health").json()["llm_host"] is None


class ProviderError(Exception):
    """What the model client raises for an HTTP error: a status code and the response with its headers."""

    def __init__(self, status_code, headers=None):
        super().__init__(f"HTTP {status_code}")
        self.status_code, self.response = status_code, SimpleNamespace(headers=headers or {})


class FlakyLLM(FakeLLM):
    """Fails with the given errors one after the other, then answers."""

    def __init__(self, *errors):
        super().__init__()
        self.errors = list(errors)

    def chat(self, messages, **kwargs):
        if self.errors:
            self.calls += 1
            raise self.errors.pop(0)
        return super().chat(messages, **kwargs)


def test_a_busy_provider_is_a_503_with_the_wait_it_names_and_the_articles(make):
    client = make(FakeLLM(error=ProviderError(429, {"x-ratelimit-reset-tokens": "7s212ms"})))
    reply = client.post("/ask", json={"question": "Quelle durée pour un cadre ?"})
    assert reply.status_code == 503 and reply.headers["Retry-After"] == "8"
    assert reply.json()["outcome"] == "llm_error" and reply.json()["articles"]


def test_health_says_when_the_model_keeps_failing_and_one_good_answer_clears_it(make):
    client = make(FlakyLLM(ProviderError(401), ProviderError(401), ProviderError(401)))
    for i in range(3):
        assert client.post("/ask", json={"question": f"Quelle durée pour le cas {i} ?"}).status_code == 502
    assert client.get("/health").json()["llm_failing"] is True
    assert client.post("/ask", json={"question": "Quelle durée pour un cadre ?"}).status_code == 200
    assert client.get("/health").json()["llm_failing"] is False


def test_health_names_another_model_once_a_reply_carries_a_name_that_was_not_asked_for(make):
    same = make(FakeLLM(served="deepseek-flash"))
    assert same.post("/ask", json={"question": "Quelle durée pour un cadre ?"}).status_code == 200
    assert same.get("/health").json()["llm_other_model"] is None
    other = make(FakeLLM(served="replacement-1"))
    assert other.post("/ask", json={"question": "Quelle durée pour un ouvrier ?"}).status_code == 200  # another question: not from the cache
    assert other.get("/health").json()["llm_other_model"] == "replacement-1"


def database_down():
    raise psycopg.OperationalError("the database is down")


def test_health_is_a_503_when_the_database_is_down():
    engine = rag.AnswerEngine(retriever=FakeRetriever([node()]), postprocessor=rag.NumberUnits(), llm=FakeLLM(), prompt=PROMPT,
                              model="deepseek-flash", prompt_id="answer.v3")
    reply = TestClient(web.create_app(engine, database_down)).get("/health")
    assert reply.status_code == 503 and reply.json() == {
        "status": "database_unavailable", "llm_enabled": None, "cache_warm": None, "llm_host": None, "llm_failing": None,
        "llm_other_model": None}


def test_a_cached_entry_made_for_another_version_of_the_reply_shape_is_a_miss(url, conn, make):
    llm = FakeLLM()
    client = make(llm)
    key = asking.cache_key(engine_for(url), web.Settings(), ASK["question"])
    cache.put(conn, key, "answered", {"outcome": "answered", "a_field_that_no_longer_exists": 1})
    reply = client.post("/ask", json=ASK).json()
    assert reply["cached"] is False and reply["outcome"] == "answered" and llm.calls == 1


def test_the_window_of_recent_events_forgets_after_its_time():
    recent = web.Recent(2, seconds=60)
    assert [recent.allow("a", now=t) for t in (0, 1, 2)] == [True, True, False]
    assert recent.retry_after("a", now=10) == 50 and recent.retry_after("nobody", now=10) == 1  # the event of t=0 leaves at 60
    assert recent.allow("b", now=2) and recent.allow("a", now=61)


def test_the_embedder_lets_only_a_few_calls_in_together():
    inside, peak, lock = 0, 0, threading.Lock()

    class Slow:
        def encode_queries(self, texts, batch_size):
            nonlocal inside, peak
            with lock:
                inside += 1
                peak = max(peak, inside)
            time.sleep(0.05)
            with lock:
                inside -= 1

    embedder = build.LimitedEmbedder(Slow(), at_once=2)
    threads = [threading.Thread(target=embedder.encode_queries, args=(["q"], 1)) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert peak == 2


ASK = {"question": "Quelle durée pour un cadre ?"}


def cached_entries(conn):
    return conn.execute("SELECT count(*) FROM answer_cache").fetchone()[0]


def test_the_same_question_twice_costs_one_model_call_and_the_second_reply_says_it_is_cached(make, conn):
    llm = FakeLLM()
    client = make(llm)
    first = client.post("/ask", json=ASK).json()
    second = client.post("/ask", json={"question": "  QUELLE durée pour un CADRE ?  "}).json()  # the same after normalising
    assert llm.calls == 1 and first["cached"] is False and second["cached"] is True
    assert second["request_id"] != first["request_id"]
    assert {k: v for k, v in second.items() if k not in ("request_id", "cached")} == {k: v for k, v in first.items() if k not in ("request_id", "cached")}
    mode, outcome, _, _, text = traced(conn, second["request_id"])
    assert (mode, outcome, text) == ("answer", "cache_hit", None)
    keys = conn.execute("SELECT cache_key, cost_usd FROM query_traces WHERE request_id IN (%s, %s) ORDER BY id",
                        (first["request_id"], second["request_id"])).fetchall()
    assert keys[0][0] == keys[1][0] and keys[0][0] and keys[1][1] == 0


def test_a_refusal_by_the_model_is_cached_too(make):
    llm = FakeLLM(REFUSAL)
    client = make(llm)
    client.post("/ask", json=ASK)
    second = client.post("/ask", json=ASK).json()
    assert llm.calls == 1 and second["cached"] is True and second["outcome"] == "refused_by_model"


def test_a_weak_search_and_a_model_failure_are_never_cached(make, conn):
    assert make(nodes=[node(0.40)]).post("/ask", json=ASK).json()["outcome"] == "refused_weak_retrieval"
    assert make(FakeLLM(error=TimeoutError())).post("/ask", json=ASK).status_code == 502
    assert cached_entries(conn) == 0


def test_another_code_version_does_not_find_the_reply_of_an_older_one(make):
    llm = FakeLLM()
    old = make(llm, settings=web.Settings(code_version="v1"))
    old.post("/ask", json=ASK)
    new = make(llm, settings=web.Settings(code_version="v2"))
    assert new.post("/ask", json=ASK).json()["cached"] is False and llm.calls == 2
    assert old.post("/ask", json=ASK).json()["cached"] is True and llm.calls == 2


def test_a_cached_reply_is_served_when_the_model_is_off_or_the_budget_is_used_up(make, conn):
    llm = FakeLLM()
    client = make(llm)
    client.post("/ask", json=ASK)
    limits.set_llm_enabled(conn, False)
    assert client.post("/ask", json=ASK).json()["cached"] is True
    limits.set_llm_enabled(conn, True)
    conn.execute("UPDATE query_traces SET cost_usd = 1")  # the day's budget is used up
    conn.commit()
    assert client.post("/ask", json=ASK).json()["cached"] is True
    assert client.post("/ask", json={"question": "Une autre question ?"}).status_code == 503  # a new one still needs the model
    assert llm.calls == 1


def test_cached_replies_do_not_use_the_model_allowance_of_the_minute(make):
    llm = FakeLLM()
    client = make(llm)  # 5 model answers a minute
    assert [client.post("/ask", json=ASK).status_code for _ in range(6)] == [200] * 6  # one model call, five from the cache
    for i in range(4):  # the allowance is almost untouched: four more fresh questions are answered
        assert client.post("/ask", json={"question": f"Autre question {i} ?"}).status_code == 200
    assert llm.calls == 5 and client.post("/ask", json={"question": "Une sixième ?"}).status_code == 429


def test_cached_replies_have_their_own_limit_and_over_it_the_client_is_refused_without_a_model_call(make, conn):
    llm = FakeLLM()
    client = make(llm, limit_settings=limits.Settings(per_minute_cached=3))
    statuses = [client.post("/ask", json=ASK).status_code for _ in range(4)]  # one model answer, then 3 cached replies
    refused = client.post("/ask", json=ASK)
    assert statuses == [200] * 4 and refused.status_code == 429 and llm.calls == 1
    body = refused.json()
    assert body["outcome"] == "rate_limited" and "cached replies" in body["reason"] and body["articles"] and int(refused.headers["Retry-After"]) >= 1
    assert traced(conn, body["request_id"])[1] == "rate_limited"
    assert client.post("/ask", json={"question": "Une autre question ?"}).status_code == 200  # a fresh question is not blocked


def test_search_is_limited_per_client_and_the_wait_is_told(make):
    behind = make(settings=web.Settings(client_ip_header="x-forwarded-for", search_per_minute=3))
    alice, bob = {"x-forwarded-for": "203.0.113.7"}, {"x-forwarded-for": "198.51.100.2"}
    assert [behind.post("/search", json=ASK, headers=alice).status_code for _ in range(3)] == [200] * 3
    refused = behind.post("/search", json=ASK, headers=alice)
    assert refused.status_code == 429 and 1 <= int(refused.headers["Retry-After"]) <= 60
    assert behind.post("/search", json=ASK, headers=bob).status_code == 200  # another client is not affected
    assert behind.post("/ask", json=ASK, headers=alice).status_code == 200  # nor is /ask for the same client


def test_a_thumbs_down_from_the_client_who_got_the_reply_removes_it_from_the_cache(make, conn):
    client = make()
    request_id = client.post("/ask", json=ASK).json()["request_id"]
    client.post("/feedback", json={"request_id": request_id, "value": 1})
    assert cached_entries(conn) == 1  # a thumbs up keeps it
    client.post("/feedback", json={"request_id": request_id, "value": -1})
    assert cached_entries(conn) == 0


def test_only_the_visitor_whom_the_model_answered_can_remove_a_stored_answer_with_a_thumbs_down(make, conn):
    behind = make(settings=web.Settings(client_ip_header="x-forwarded-for"))
    alice, bob, carol = ({"x-forwarded-for": address} for address in ("203.0.113.7", "198.51.100.2", "192.0.2.9"))
    first = behind.post("/ask", json=ASK, headers=alice).json()["request_id"]
    behind.post("/feedback", json={"request_id": first, "value": -1}, headers=bob)
    assert cached_entries(conn) == 1  # bob did not get alice's reply
    served = behind.post("/ask", json=ASK, headers=bob).json()
    assert served["cached"] is True
    behind.post("/feedback", json={"request_id": served["request_id"], "value": -1}, headers=bob)
    assert cached_entries(conn) == 1  # bob received a stored reply: he did not pay for it, so his vote cannot clear it for everyone
    behind.post("/feedback", json={"request_id": first, "value": -1}, headers=alice)
    assert cached_entries(conn) == 0  # alice was answered by the model: her vote removes the entry
    assert behind.post("/ask", json=ASK, headers=carol).json()["cached"] is False  # the next visitor gets a fresh answer


def test_the_warm_up_asks_each_example_once_without_the_client_limits_and_skips_the_cached_ones(url, conn, make):
    make()  # empties the tables
    llm, connect, settings = FakeLLM(), partial(db.connect, url), web.Settings()
    engine = engine_for(url, llm)
    questions = [f"Question {i} ?" for i in range(7)]  # more than the 5 a minute of one client
    status = warm.run(engine, connect, settings, questions, warm.Status())
    assert (status.state, status.asked, status.stored, status.skipped, status.stopped) == ("done", 7, 7, 0, None)
    assert llm.calls == 7 and cached_entries(conn) == 7
    assert conn.execute("SELECT count(*) FROM query_traces WHERE client_hash IS NOT NULL").fetchone()[0] == 0
    again = warm.run(engine, connect, settings, [*questions[:2], "Question neuve ?"], warm.Status())
    assert (again.asked, again.skipped) == (1, 2) and llm.calls == 8
    assert TestClient(web.create_app(engine, connect, settings)).post("/ask", json={"question": questions[0]}).json()["cached"]


def test_the_warmed_examples_are_pinned_and_a_thumbs_down_keeps_them_but_the_vote_is_saved(url, conn, make):
    client = make()
    warm.run(engine_for(url), partial(db.connect, url), web.Settings(), [ASK["question"]], warm.Status())
    assert conn.execute("SELECT pinned, expires_at > now() + interval '100 years' FROM answer_cache").fetchone() == (True, True)
    served = client.post("/ask", json=ASK).json()  # a visitor clicks the example
    assert served["cached"] is True
    client.post("/feedback", json={"request_id": served["request_id"], "value": -1, "kind": "wrong_answer"})
    assert cached_entries(conn) == 1  # the example stays
    assert conn.execute("SELECT feedback, feedback_kind FROM query_traces WHERE request_id = %s", (served["request_id"],)).fetchone() == (-1, "wrong_answer")


def test_an_example_that_a_visitor_already_caused_to_be_stored_is_pinned_and_not_asked_again(url, conn, make):
    llm = FakeLLM()
    client = make(llm)
    client.post("/ask", json=ASK)  # a visitor types the same question first
    assert conn.execute("SELECT pinned FROM answer_cache").fetchone() == (False,)
    status = warm.run(engine_for(url, llm), partial(db.connect, url), web.Settings(), [ASK["question"]], warm.Status())
    assert (status.asked, status.skipped, llm.calls) == (0, 1, 1)
    assert conn.execute("SELECT pinned FROM answer_cache").fetchone() == (True,)


def test_the_warm_up_stops_when_the_model_is_off_and_never_raises(url, conn, make):
    make()
    connect, settings = partial(db.connect, url), web.Settings()
    limits.set_llm_enabled(conn, False)
    stopped = warm.run(engine_for(url), connect, settings, ["Question 1 ?", "Question 2 ?"], warm.Status())
    assert (stopped.state, stopped.asked, stopped.stored, stopped.stopped) == ("done", 1, 0, "llm_disabled")
    broken = warm.run(engine_for(url), database_down, settings, ["Question 1 ?"], warm.Status())
    assert (broken.state, broken.stopped) == ("done", "OperationalError")


def test_the_service_warms_the_cache_in_the_background_at_startup(make):
    llm = FakeLLM()
    with make(llm, warm=["Question une ?"]) as client:  # the `with` runs the startup of the app
        for _ in range(100):
            if client.get("/health").json()["cache_warm"] == "done":
                break
            time.sleep(0.05)
        assert client.get("/health").json()["cache_warm"] == "done" and llm.calls == 1
        assert client.post("/ask", json={"question": "Question une ?"}).json()["cached"] is True


def test_the_example_questions_are_read_from_a_yaml_file(tmp_path):
    path = tmp_path / "examples.yaml"
    path.write_text("questions:\n  - ' Quelle durée ? '\n  - Que dit la loi ?\n")
    assert warm.load_questions(path) == ["Quelle durée ?", "Que dit la loi ?"]
    path.write_text("- Quelle durée ?\n")
    assert warm.load_questions(path) == ["Quelle durée ?"]
    path.write_text("questions: [1, 2]\n")
    with pytest.raises(ValueError, match="list of questions"):
        warm.load_questions(path)
