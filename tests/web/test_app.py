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
    def __init__(self, reply=GOOD, error=None):
        self.reply, self.error, self.calls = reply, error, 0

    def chat(self, messages, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        usage = SimpleNamespace(prompt_tokens=1100, completion_tokens=90, prompt_cache_hit_tokens=1000)
        return SimpleNamespace(message=SimpleNamespace(content=self.reply), raw=SimpleNamespace(usage=usage))


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
        threshold=threshold, gate=limits.Limits(lambda: db.connect(url), limit_settings) if gate else None)


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
    first = behind.post("/ask", json=ask, headers={"x-forwarded-for": "203.0.113.7, 10.0.0.1"}).json()["request_id"]
    again = behind.post("/ask", json=ask, headers={"x-forwarded-for": "203.0.113.7"}).json()["request_id"]
    other = behind.post("/ask", json=ask, headers={"x-forwarded-for": "198.51.100.2"}).json()["request_id"]
    assert traced(conn, first)[2] == traced(conn, again)[2] != traced(conn, other)[2]
    direct = make().post("/ask", json=ask, headers={"x-forwarded-for": "203.0.113.7"}).json()["request_id"]
    assert traced(conn, direct)[2] != traced(conn, first)[2]  # without a named header the connection address counts


def test_a_failed_trace_write_does_not_break_the_answer(make, monkeypatch):
    client = make()
    monkeypatch.setattr(trace, "record", lambda conn, row: (_ for _ in ()).throw(RuntimeError("disk full")))
    assert client.post("/ask", json={"question": "Quelle durée ?"}).status_code == 200


def test_health_says_whether_written_answers_are_on(make, conn):
    client = make()
    assert client.get("/health").json() == {"status": "ok", "llm_enabled": True, "cache_warm": "off"}
    limits.set_llm_enabled(conn, False)
    assert client.get("/health").json() == {"status": "ok", "llm_enabled": False, "cache_warm": "off"}


def database_down():
    raise psycopg.OperationalError("the database is down")


def test_health_is_a_503_when_the_database_is_down():
    engine = rag.AnswerEngine(retriever=FakeRetriever([node()]), postprocessor=rag.NumberUnits(), llm=FakeLLM(), prompt=PROMPT,
                              model="deepseek-flash", prompt_id="answer.v3")
    reply = TestClient(web.create_app(engine, database_down)).get("/health")
    assert reply.status_code == 503 and reply.json() == {"status": "database_unavailable", "llm_enabled": None, "cache_warm": None}


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


def test_a_thumbs_down_from_another_client_leaves_the_cache_alone_and_one_on_a_cached_reply_removes_it(make, conn):
    behind = make(settings=web.Settings(client_ip_header="x-forwarded-for"))
    alice, bob = {"x-forwarded-for": "203.0.113.7"}, {"x-forwarded-for": "198.51.100.2"}
    first = behind.post("/ask", json=ASK, headers=alice).json()["request_id"]
    behind.post("/feedback", json={"request_id": first, "value": -1}, headers=bob)
    assert cached_entries(conn) == 1  # bob did not get alice's reply
    served = behind.post("/ask", json=ASK, headers=bob).json()
    assert served["cached"] is True
    behind.post("/feedback", json={"request_id": served["request_id"], "value": -1}, headers=bob)
    assert cached_entries(conn) == 0  # bob got that reply, from the cache


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
