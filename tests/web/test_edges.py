"""Edge cases of the service: what a visitor, a script or a broken part can send or cause. Each test names the behaviour
that is wanted. They use the fixtures of test_app (a fake search, a fake model, a throwaway database)."""
# ruff: noqa: F811 - a fixture imported from test_app is named again as an argument of the tests: that is how pytest uses it

import json
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest
from fastapi.testclient import TestClient
from test_app import (  # noqa: F401 - fixtures
    FRENCH,
    GOOD,
    FakeLLM,
    ScriptedLLM,
    engine_for,
    make,
    secret,
    traced,
    translate,
    url,
)

from legalrag.answering import limits
from legalrag.index import db
from legalrag.web import app as web
from legalrag.web import asking


def post(client, path, body, headers=None):
    """A POST with the body written as it is: what a browser would never send."""
    return client.post(path, content=body, headers={"content-type": "application/json", **(headers or {})})


def ask_as(client, address, question):
    return client.post("/ask", json={"question": question}, headers={"x-real": address})


# ---- what the questions and the comments may contain ----

@pytest.mark.parametrize("body", [
    "", "null", "[]", "{}", '"text"', "123", "{not json", '{"question": null}', '{"question": 123}', '{"question": ["a"]}',
    '{"question": ""}', '{"question": "   "}', '{"question": "\\u0000"}', '{"question": "\\u0000\\u0007\\u001b"}',
    '{"question": "\\ud800"}', '{"question": "\\udfff abc"}', '{"question": "ok", "lang": "en"}',
    '{"question": "ok", "translate": "yes"}', '{"question": "ok", "translate": 1}', '{"question": "ok", "translate": null}',
])
def test_a_malformed_question_is_a_422_and_nothing_is_traced(make, conn, body):
    assert post(make(), "/ask", body).status_code == 422, body
    assert conn.execute("SELECT count(*) FROM query_traces").fetchone()[0] == 0


def test_a_422_never_repeats_what_the_visitor_sent(make):
    reply = post(make(), "/ask", '{"question": "' + "secret" * 100 + '"}')  # 600 characters: too long
    assert reply.status_code == 422 and "secret" not in reply.text
    reply = post(make(), "/ask", '{"question": "\\ud800 secret"}')  # a lone surrogate cannot even be written back
    assert reply.status_code == 422 and "secret" not in reply.text


def test_the_longest_question_is_accepted_in_any_alphabet(make):
    c = make()
    for question in ("é" * 500, "😀" * 500, "律" * 500, "a" * 500, "a" * 250 + " " + "b" * 249):
        assert c.post("/ask", json={"question": question}).status_code == 200, question[:5]


def test_control_characters_are_dropped_and_newlines_kept(make, conn):
    body = make().post("/ask", json={"question": "Quelle\u0000 durée\u0007 ?\nEt le préavis\t?\x1b"}).json()
    assert traced(conn, body["request_id"])[3] == "Quelle durée ?\nEt le préavis\t?"


def test_html_and_sql_in_a_question_are_kept_as_text_and_never_run(make, conn):
    c = make()
    for question in ("<script>alert(1)</script> Quelle durée ?", "'; DROP TABLE query_traces; -- Quelle durée ?",
                     "Robert'); DELETE FROM answer_cache;-- ?", '"><img src=x onerror=alert(1)>', "{{7*7}} ${7*7} %s %(x)s"):
        reply = c.post("/ask", json={"question": question})
        assert reply.status_code == 200 and reply.headers["content-type"].startswith("application/json")
        assert traced(conn, reply.json()["request_id"])[3] == question
    assert conn.execute("SELECT count(*) FROM query_traces").fetchone()[0] == 5  # the table and its rows are still there


def test_a_question_with_decomposed_accents_shares_the_answer_of_the_composed_one(make):
    llm = FakeLLM()
    c = make(llm)
    composed = "Quelle est la durée du préavis ?"
    decomposed = unicodedata.normalize("NFD", composed)
    assert decomposed != composed
    c.post("/ask", json={"question": composed})
    assert c.post("/ask", json={"question": decomposed}).json()["cached"] and llm.calls == 1


def test_a_fullwidth_or_hidden_identifier_is_masked_before_anything_is_stored(make, conn):
    c = make()
    for hidden in ("ｊｅａｎ＠ｅｘａｍｐｌｅ．ｃｏｍ", "jean@exam\u200bple.com", "06\u200b 12 34\u2060 56 78", "０６ １２ ３４ ５６ ７８"):
        body = c.post("/ask", json={"question": f"Mon contact : {hidden} merci"}).json()
        assert body["masked"], hidden
        assert "exam" not in traced(conn, body["request_id"])[3] and "56" not in traced(conn, body["request_id"])[3]


def test_a_comment_with_a_nul_or_a_lone_surrogate_does_not_break_the_vote(make, conn):
    c = make()
    answer = c.post("/ask", json={"question": FRENCH}).json()
    ok = c.post("/feedback", json={"request_id": answer["request_id"], "value": -1, "comment": "faux\u0000 merci"})
    assert ok.status_code == 200
    assert conn.execute("SELECT feedback_comment FROM query_traces WHERE request_id = %s", (answer["request_id"],)).fetchone()[0] == "faux merci"
    bad = post(c, "/feedback", '{"request_id": "' + answer["request_id"] + '", "value": -1, "comment": "\\ud800"}')
    assert bad.status_code == 422


@pytest.mark.parametrize("request_id", ["x'; DROP TABLE query_traces;--", "a b", "é", "../../etc/passwd", "a" * 65, "", "%s", "1 OR 1=1"])
def test_a_request_id_is_only_looked_up_when_it_looks_like_one(make, conn, request_id):
    c = make()
    assert c.post("/feedback", json={"request_id": request_id, "value": 1}).status_code == 422
    assert c.post("/translate-answer", json={"request_id": request_id}).status_code == 422
    assert conn.execute("SELECT count(*) FROM information_schema.tables WHERE table_name = 'query_traces'").fetchone()[0] == 1


@pytest.mark.parametrize("value", ["1", "-1", 0, 2, None, True, 1.5, [1]])
def test_a_vote_is_exactly_1_or_minus_1(make, value):
    answer = make().post("/ask", json={"question": FRENCH}).json()
    c = make()
    code = c.post("/feedback", json={"request_id": answer["request_id"], "value": value}).status_code
    assert code in (404, 422)  # never a stored vote: the request is unknown to this second app, or the value is refused


# ---- sizes, methods, paths, headers ----

def test_a_body_that_declares_chunked_framing_is_refused_whatever_length_it_declares(make):
    """The server reads a chunked body to its end and ignores Content-Length: a small declared length hid a body of 8 MB."""
    c = make()
    for headers in ({"transfer-encoding": "chunked"}, {"transfer-encoding": "chunked", "content-length": "1"},
                    {"Transfer-Encoding": "gzip, chunked"}, {"transfer-encoding": "identity"}):
        reply = post(c, "/ask", '{"question": "Quelle durée ?"}', headers)
        assert reply.status_code == 411, headers
    assert post(c, "/feedback", "{}", {"transfer-encoding": "chunked"}).status_code == 411


def test_a_large_or_unmeasured_body_is_refused_before_it_is_read(make):
    c = make()
    assert post(c, "/ask", '{"question": "' + "a" * 20000 + '"}').status_code == 413
    assert post(c, "/feedback", "x" * 20000).status_code == 413
    assert post(c, "/translate-answer", "x" * 20000).status_code == 413
    chunks = iter(['{"question": "Quelle durée ?"}'.encode()])  # no content-length: sent in chunks
    assert c.post("/ask", content=chunks, headers={"content-type": "application/json"}).status_code == 411
    assert post(c, "/ask", '{"question": "' + "a" * 400 + '"}').status_code == 200  # a normal body is not in the way


@pytest.mark.parametrize("path", [
    "/static/../app.py", "/static/%2e%2e/app.py", "/static/..%2fapp.py", "/static//etc/passwd", "/static/%00", "/static/app.js/..",
    "/static/..\\app.py", "/static/", "/static", "/static/.env", "/static/index.html%00.js", "/static/%252e%252e/app.py",
    "/static/./../../pyproject.toml", "/static/c:/windows/win.ini",
])
def test_the_static_route_serves_only_its_own_files(make, path):
    reply = make().get(path)
    assert reply.status_code != 200 and reply.status_code < 500
    assert "legalrag" not in reply.text.lower() or reply.status_code == 404


@pytest.mark.parametrize("method, path", [
    ("GET", "/ask"), ("GET", "/feedback"), ("GET", "/translate-answer"), ("POST", "/"), ("POST", "/method"), ("POST", "/history"),
    ("DELETE", "/ask"), ("PUT", "/feedback"), ("POST", "/health"), ("PATCH", "/ask"), ("POST", "/examples"),
])
def test_a_route_refuses_the_methods_it_does_not_serve(make, method, path):
    assert make().request(method, path, content="{}", headers={"content-type": "application/json"}).status_code == 405


def test_every_reply_even_an_error_has_the_security_headers(make):
    c = make()
    replies = (c.get("/nowhere"), post(c, "/ask", "{}"), post(c, "/ask", "x" * 20000), c.get("/static/missing"), c.get("/ask"),
               c.get("/health"), c.get("/"), c.get("/history"))
    for reply in replies:
        assert reply.headers["x-frame-options"] == "DENY" and "camera=()" in reply.headers["permissions-policy"]
        assert reply.headers["referrer-policy"] == "no-referrer" and "cache-control" in reply.headers
        assert reply.headers["x-content-type-options"] == "nosniff"
        assert "default-src 'self'" in reply.headers["content-security-policy"] and "frame-ancestors 'none'" in reply.headers["content-security-policy"]


def test_the_client_header_takes_the_last_address_and_an_empty_or_huge_one_does_no_harm(make):
    c = make(settings=asking.Settings(client_ip_header="x-real"), limit_settings=limits.Settings(per_minute=1, per_day=30, cost_per_day_usd=0.10))
    assert ask_as(c, "9.9.9.9, 1.1.1.1", "Q une ?").status_code == 200
    assert ask_as(c, "8.8.8.8, 1.1.1.1", "Q deux ?").status_code == 429  # the same last address: the same visitor, whatever they wrote first
    assert ask_as(c, "1.1.1.1, 2.2.2.2", "Q trois ?").status_code == 200  # another visitor
    assert ask_as(c, "", "Q quatre ?").status_code == 200  # an empty header: the address of the connection
    assert ask_as(c, "", "Q cinq ?").status_code == 429
    assert ask_as(c, "9.9.9.9, " * 2000 + "3.3.3.3", "Q six ?").status_code == 200


def test_a_forged_client_header_is_ignored_when_none_is_named(make):
    c = make(limit_settings=limits.Settings(per_minute=1, per_day=30, cost_per_day_usd=0.10))
    assert ask_as(c, "1.1.1.1", "Q une ?").status_code == 200
    assert ask_as(c, "2.2.2.2", "Q deux ?").status_code == 429  # changing the header does not make a new visitor


# ---- failures of the parts ----

def broken_app(url, **changes):
    """An app whose search raises an error that carries a secret, and a client that shows the 500 instead of raising it."""
    engine = engine_for(url)
    for name, value in changes.items():
        setattr(engine, name, value)
    return engine


def test_an_unexpected_error_is_a_plain_500_without_details(url):
    from llama_index.core.retrievers import BaseRetriever

    class Broken(BaseRetriever):
        def _retrieve(self, query_bundle):
            raise RuntimeError("secret internal detail password=hunter2")

    client = TestClient(web.create_app(broken_app(url, retriever=Broken()), lambda: db.connect(url)), raise_server_exceptions=False)
    reply = client.post("/ask", json={"question": FRENCH})
    assert reply.status_code == 500 and "hunter2" not in reply.text and "secret" not in reply.text and "Traceback" not in reply.text


def failing_connect():
    raise psycopg.OperationalError("connection to server failed: password=hunter2")


def test_when_the_database_of_the_limits_is_down_the_model_is_not_called_and_nothing_leaks(url):
    llm = FakeLLM()
    engine = engine_for(url, llm)
    engine.gate = limits.Limits(failing_connect)
    client = TestClient(web.create_app(engine, lambda: db.connect(url)), raise_server_exceptions=False)
    reply = client.post("/ask", json={"question": FRENCH})
    assert reply.status_code == 503 and "hunter2" not in reply.text and reply.headers["retry-after"] == "30"
    assert llm.calls == 0  # fail closed: without the counts nothing is spent


def test_when_the_database_of_traces_and_cache_is_down_the_answer_still_arrives_and_a_vote_says_503(url):
    client = TestClient(web.create_app(engine_for(url), failing_connect), raise_server_exceptions=False)
    assert client.post("/ask", json={"question": FRENCH}).status_code == 200  # the trace and the cache are optional
    vote = client.post("/feedback", json={"request_id": "a" * 32, "value": 1})
    assert vote.status_code == 503 and "hunter2" not in vote.text
    assert client.get("/health").status_code == 503


# ---- bursts and abuse ----

class SlowLLM(FakeLLM):
    def chat(self, messages, **kwargs):
        time.sleep(0.4)
        return super().chat(messages, **kwargs)


def test_a_burst_of_parallel_requests_from_one_visitor_cannot_pass_the_limit(make):
    llm = SlowLLM()
    c = make(llm, limit_settings=limits.Settings(per_minute=2, per_day=30, cost_per_day_usd=0.10))
    with ThreadPoolExecutor(12) as pool:
        replies = list(pool.map(lambda i: c.post("/ask", json={"question": f"Question numéro {i} ?"}), range(12)))
    codes = sorted(r.status_code for r in replies)
    assert set(codes) <= {200, 429} and llm.calls <= 2  # before the fix all twelve passed the check together
    busy = [r for r in replies if r.status_code == 429 and "en cours" in (r.json().get("reason") or "")]
    assert busy and all(int(r.headers["retry-after"]) >= 1 for r in busy)
    assert all(r.json()["busy"] is True and "depuis votre connexion" in r.json()["reason"] for r in busy)  # the page words this case itself


def test_the_slot_of_a_visitor_is_freed_after_an_error_so_that_the_next_request_works(url):
    from llama_index.core.retrievers import BaseRetriever

    class Once(BaseRetriever):
        calls = 0

        def _retrieve(self, query_bundle):
            Once.calls += 1
            if Once.calls == 1:
                raise RuntimeError("first request fails")
            return [__import__("test_app").node()]

    engine = broken_app(url, retriever=Once())
    client = TestClient(web.create_app(engine, lambda: db.connect(url)), raise_server_exceptions=False)
    assert client.post("/ask", json={"question": "Première ?"}).status_code == 500
    assert client.post("/ask", json={"question": "Deuxième ?"}).status_code == 200  # not "already in progress"
    assert not engine.gate.busy


def test_requests_of_different_visitors_do_not_wait_for_each_other(make):
    llm = SlowLLM()
    c = make(llm, settings=asking.Settings(client_ip_header="x-real"))
    started = time.monotonic()
    with ThreadPoolExecutor(4) as pool:
        replies = list(pool.map(lambda i: ask_as(c, f"10.0.0.{i}", f"Question numéro {i} ?"), range(4)))
    assert [r.status_code for r in replies] == [200] * 4 and time.monotonic() - started < 1.4  # four times 0.4 s in parallel, not in a row


def test_parallel_votes_and_translations_of_one_visitor_stay_within_their_limits(make):
    llm = ScriptedLLM(*([GOOD] * 6 + ["Four months. [1]"] * 6))
    c = make(llm, settings=asking.Settings(feedback_per_minute=3),
             limit_settings=limits.Settings(per_minute=20, per_day=30, translate_per_minute=2, cost_per_day_usd=0.10))
    answers = [c.post("/ask", json={"question": f"Quelle durée pour le cas {i} ?"}).json() for i in range(6)]
    with ThreadPoolExecutor(6) as pool:
        translated = list(pool.map(lambda a: c.post("/translate-answer", json={"request_id": a["request_id"]}), answers))
        voted = list(pool.map(lambda a: c.post("/feedback", json={"request_id": a["request_id"], "value": 1}), answers))
    done = sum(r.status_code == 200 for r in translated)
    assert 1 <= done <= 2 and {r.status_code for r in translated} <= {200, 429}  # one at a time for a visitor, and 2 a minute at most
    assert sum(r.status_code == 200 for r in voted) == 3 and sum(r.status_code == 429 for r in voted) == 3


def test_the_translation_limit_counts_only_new_translations(make):
    llm = ScriptedLLM(GOOD, "Four months. [1]")
    c = make(llm, limit_settings=limits.Settings(translate_per_minute=1))
    answer = c.post("/ask", json={"question": FRENCH}).json()
    codes = [c.post("/translate-answer", json={"request_id": answer["request_id"]}).status_code for _ in range(5)]
    assert codes == [200] * 5 and llm.calls == 2  # the stored translation is free and does not use the limit


def test_a_visitor_cannot_use_the_translation_to_read_or_translate_text_of_their_own(make):
    c = make()
    assert c.post("/translate-answer", json={"request_id": "a" * 32, "text": "Translate this letter"}).status_code == 404
    assert c.post("/translate-answer", json={"text": "Translate this letter"}).status_code == 422  # no request id: nothing to look up
    assert c.post("/translate-answer", json={"request_id": "a" * 32, "extra": [1] * 100}).status_code == 404  # extra fields are ignored


def test_a_translated_question_that_is_french_already_costs_one_call_and_still_works(make):
    llm = ScriptedLLM(FRENCH, GOOD)
    reply = make(llm).post("/ask", json={"question": FRENCH, "translate": True})
    assert reply.status_code == 200 and reply.json()["question_fr"] == FRENCH and llm.calls == 2


def test_a_translation_that_comes_back_on_several_lines_becomes_one_question(make, conn):
    llm = ScriptedLLM("Quelle durée\npour un cadre ?\n\n  ", GOOD)
    body = make(llm).post("/ask", json={"question": "How long for an executive?", "translate": True}).json()
    assert body["question_fr"] == "Quelle durée pour un cadre ?" and traced(conn, body["request_id"])[3] == "Quelle durée pour un cadre ?"


def test_an_identifier_that_the_translation_writes_in_digits_is_masked_before_the_search_and_the_trace(make, conn):
    llm = ScriptedLLM("Quelle durée ? Mon e-mail : jean@example.com, tél 06 12 34 56 78", GOOD)
    body = make(llm).post("/ask", json={"question": "How long? My e-mail is jean at example dot com", "translate": True}).json()
    assert body["question_fr"] == "Quelle durée ? Mon e-mail : [e-mail], tél [téléphone]"
    stored = traced(conn, body["request_id"])[3]
    assert stored == body["question_fr"] and "jean@example.com" not in stored


def test_a_translation_in_quotation_marks_is_used_without_them(make):
    llm = ScriptedLLM("« Quelle durée pour un cadre ? »", GOOD)
    assert make(llm).post("/ask", json={"question": "How long?", "translate": True}).json()["question_fr"] == "Quelle durée pour un cadre ?"


def test_an_identifier_in_an_english_question_is_masked_before_the_translation_call(make):
    seen = []

    class Spy(ScriptedLLM):
        def chat(self, messages, **kwargs):
            seen.append(messages[-1].content)
            return super().chat(messages, **kwargs)

    llm = Spy("Quelle durée ? Mon e-mail est [e-mail]", GOOD)
    make(llm).post("/ask", json={"question": "How long? My e-mail is jean@example.com", "translate": True})
    assert "jean@example.com" not in seen[0] and "[e-mail]" in seen[0]  # the model that translates never sees the address


def test_the_same_new_question_asked_by_many_visitors_at_once_calls_the_model_once(make):
    """Twenty visitors asking the same new question used to cause twenty model calls for one stored answer."""
    llm = SlowLLM()
    c = make(llm, settings=asking.Settings(client_ip_header="x-real"))
    with ThreadPoolExecutor(10) as pool:
        replies = list(pool.map(lambda i: ask_as(c, f"10.8.0.{i}", FRENCH).json(), range(10)))
    assert llm.calls == 1 and sorted(r["outcome"] for r in replies) == ["answered"] * 10
    assert sorted(r["cached"] for r in replies) == [False] + [True] * 9  # one visitor paid, the nine others read it


def test_the_same_answer_translated_by_many_visitors_at_once_is_translated_once(make):
    class SlowTranslation(ScriptedLLM):
        def chat(self, messages, **kwargs):
            time.sleep(0.3)
            return super().chat(messages, **kwargs)

    llm = SlowTranslation(GOOD, "Four months. [1]", "never used")
    c = make(llm, settings=asking.Settings(client_ip_header="x-real"))
    answer = ask_as(c, "10.9.0.0", FRENCH).json()
    with ThreadPoolExecutor(8) as pool:
        replies = list(pool.map(lambda i: c.post("/translate-answer", json={"request_id": answer["request_id"]},
                                                 headers={"x-real": f"10.9.1.{i}"}), range(8)))
    assert llm.calls == 2 and [r.status_code for r in replies] == [200] * 8  # the answer and one translation, for eight visitors
    assert sorted(r.json()["stored"] for r in replies) == [False] + [True] * 7


def test_the_translation_of_answers_has_a_daily_cap_and_a_stored_one_is_free(make):
    llm = ScriptedLLM(*([GOOD] * 4 + ["Four months. [1]"] * 4))
    c = make(llm, limit_settings=limits.Settings(per_minute=20, translate_per_minute=20, translate_per_day=2, cost_per_day_usd=0.10))
    answers = [c.post("/ask", json={"question": f"Quelle durée pour le cas {i} ?"}).json() for i in range(4)]
    codes = [translate(c, a).status_code for a in answers]
    assert codes == [200, 200, 429, 429]
    assert translate(c, answers[0]).status_code == 200  # already stored: not counted again


def test_a_search_queue_that_is_full_refuses_at_once_and_recovers():
    import numpy as np

    from legalrag.web import build

    class Slow:
        def encode_queries(self, texts, batch_size):
            time.sleep(0.3)
            return np.ones((len(texts), 4), dtype=np.float32)

    limited = build.LimitedEmbedder(Slow(), at_once=1, waiting=1)
    results = []

    def call():
        try:
            limited.encode_queries(["q"], 1)
            results.append("ok")
        except limits.Overloaded:
            results.append("busy")

    threads = []
    for _ in range(3):  # the first runs, the second waits, the third finds the queue full
        threads.append(threading.Thread(target=call))
        threads[-1].start()
        time.sleep(0.05)
    for t in threads:
        t.join()
    assert sorted(results) == ["busy", "ok", "ok"] and limited.waiting == 0
    limited.encode_queries(["q"], 1)  # the places are free again


def test_a_refused_search_is_a_503_with_a_wait_and_nothing_is_leaked(url):
    from llama_index.core.retrievers import BaseRetriever

    class Busy(BaseRetriever):
        def _retrieve(self, query_bundle):
            raise limits.Overloaded

    client = TestClient(web.create_app(broken_app(url, retriever=Busy()), lambda: db.connect(url)), raise_server_exceptions=False)
    for path in ("/ask", "/search"):
        reply = client.post(path, json={"question": FRENCH})
        assert reply.status_code == 503 and reply.headers["retry-after"] == "3" and "Overloaded" not in reply.text


def test_the_rate_windows_forget_addresses_with_nothing_left_in_the_window(monkeypatch):
    monkeypatch.setattr(web, "FORGET_AFTER", 10)
    window = web.Recent(5, seconds=60)
    for i in range(30):
        assert window.allow(f"a{i}", now=float(i))
    assert len(window.events) == 30  # all still inside their minute
    assert window.allow("late", now=1000.0) and len(window.events) == 1  # a lot of idle ones: forgotten
    assert window.allow("late", now=1001.0) and window.retry_after("late", now=1002.0) >= 1


def test_the_busy_slot_is_per_visitor_and_the_cache_does_not_hide_a_burst(make):
    llm = SlowLLM()
    c = make(llm)
    c.post("/ask", json={"question": FRENCH})  # now cached
    barrier = threading.Barrier(6)

    def one(i):
        barrier.wait()
        return c.post("/ask", json={"question": FRENCH}).status_code

    with ThreadPoolExecutor(6) as pool:
        codes = list(pool.map(one, range(6)))
    assert set(codes) <= {200, 429} and llm.calls == 1  # the answer is in memory: no new model call, whatever the burst


def test_json_with_duplicate_keys_or_deep_nesting_is_refused_or_ignored_and_never_a_500(make):
    c = make()
    assert post(c, "/ask", '{"question": "a", "question": "b ?"}').status_code in (200, 422)
    deep = "[" * 3000 + "]" * 3000
    assert post(c, "/ask", '{"question": ' + deep + "}").status_code == 422
    assert post(c, "/ask", json.dumps({"question": "ok ?", "translate": False, "extra": {"a": [1, 2, {"b": None}]}})).status_code == 200
