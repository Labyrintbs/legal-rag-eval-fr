import json
import threading
import time
from types import SimpleNamespace

import pytest
from conftest import with_database

pytest.importorskip("llama_index.core")
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, TextNode

from legalrag.answering import limits, rag, trace
from legalrag.index import db
from legalrag.index.config import database_url
from legalrag.web import app as web
from legalrag.web import build, schemas

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


@pytest.fixture
def make(url, conn):
    """A client of the app over the throwaway database, with a fake search and a fake model."""

    def build_client(llm=None, nodes=None, settings=None, gate=True, threshold=0.55):
        engine = rag.AnswerEngine(
            retriever=FakeRetriever(nodes if nodes is not None else [node(), node(0.65, "L1221-20")]),
            postprocessor=rag.NumberUnits(), llm=llm or FakeLLM(), prompt=PROMPT, model="deepseek-flash", prompt_id="answer.v3",
            threshold=threshold, gate=limits.Limits(lambda: db.connect(url)) if gate else None)
        return TestClient(web.create_app(engine, lambda: db.connect(url), settings))

    conn.execute("DELETE FROM query_traces")
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
    for _ in range(5):
        assert client.post("/ask", json={"question": "Quelle durée ?"}).status_code == 200
    reply = client.post("/ask", json={"question": "Quelle durée ?"})
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
    assert client.get("/health").json() == {"status": "ok", "llm_enabled": True}
    limits.set_llm_enabled(conn, False)
    assert client.get("/health").json() == {"status": "ok", "llm_enabled": False}


def test_the_window_of_recent_events_forgets_after_its_time():
    recent = web.Recent(2, seconds=60)
    assert [recent.allow("a", now=t) for t in (0, 1, 2)] == [True, True, False]
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
