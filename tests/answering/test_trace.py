import io
import json
import logging
from datetime import UTC, date, datetime, timedelta

import psycopg
import pytest
from typer.testing import CliRunner

from legalrag.answering import logs, trace
from legalrag.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def empty_table(conn):
    """record() commits, so each test empties the table afterwards."""
    yield
    conn.rollback()
    conn.execute("DELETE FROM query_traces")
    conn.commit()


def make(outcome="answered", **changes):
    base = {"request_id": trace.new_request_id(), "lang": "fr", "question": "Quelle est la durée du préavis ?",
            "mode": "answer", "outcome": outcome}
    return trace.Trace(**(base | changes))


RETRIEVED = [{"label": "L1237-1", "chunk_index": 0, "score": 0.82}, {"label": "L1237-2", "chunk_index": 0, "score": 0.70}]


def test_record_stores_the_trace_with_a_hash_and_the_score_gap(conn):
    trace_id = trace.record(conn, make(retrieved=RETRIEVED, cited=[{"label": "L1237-1", "chunk_index": 0, "unit": 2}],
                                       tokens_in=1100, tokens_out=120, cost_usd=0.0006, total_ms=1800))
    row = conn.execute("SELECT question_sha256, top_score, score_gap, retrieved, cited, tokens_in, expires_at - created_at "
                       "FROM query_traces WHERE id = %s", (trace_id,)).fetchone()
    assert len(row[0]) == 64 and row[1] == pytest.approx(0.82) and row[2] == pytest.approx(0.12)
    assert row[3][0]["label"] == "L1237-1" and row[4][0]["unit"] == 2 and row[5] == 1100
    assert row[6] == timedelta(days=30)


def test_the_outcomes_of_the_module_are_the_ones_the_table_accepts_and_no_others(conn):
    for outcome in trace.OUTCOMES:
        trace.record(conn, make(outcome))
    with pytest.raises(psycopg.errors.CheckViolation):
        trace.record(conn, make("something_else"))
    conn.rollback()
    for bad in ({"lang": "de"}, {"mode": "chat"}):
        with pytest.raises(psycopg.errors.CheckViolation):
            trace.record(conn, make(**bad))
        conn.rollback()
    assert set(trace.FAILURES) <= set(trace.OUTCOMES) and "answered" not in trace.FAILURES


def test_a_request_id_is_stored_once(conn):
    first = make()
    trace.record(conn, first)
    with pytest.raises(psycopg.errors.UniqueViolation):
        trace.record(conn, make(request_id=first.request_id))


def test_failures_lists_the_quality_failures_newest_first_and_can_filter(conn):
    trace.record(conn, make("answered"))
    trace.record(conn, make("refused_weak_retrieval", question="Q1", retrieved=RETRIEVED, refusal_reason="top score 0.31"))
    trace.record(conn, make("llm_error", question="Q2", error="TimeoutError"))
    trace.record(conn, make("rate_limited", question="Q3"))
    rows = trace.failures(conn, timedelta(days=1))
    assert [r["question"] for r in rows] == ["Q2", "Q1"]
    assert rows[1]["retrieved"][0]["label"] == "L1237-1" and rows[1]["refusal_reason"] == "top score 0.31"
    assert [r["question"] for r in trace.failures(conn, timedelta(days=1), ("rate_limited",))] == ["Q3"]
    conn.execute("UPDATE query_traces SET created_at = now() - interval '3 days'")
    assert trace.failures(conn, timedelta(days=1)) == [] and len(trace.failures(conn, timedelta(days=5))) == 2


def test_summary_counts_outcomes_and_the_cost_of_answered_requests(conn):
    for ms in (1000, 2000, 3000):
        trace.record(conn, make("answered", tokens_in=1000, tokens_out=100, cost_usd=0.001, total_ms=ms))
    trace.record(conn, make("refused_by_model"))
    s = trace.summary(conn, timedelta(days=1))
    assert s["requests"] == 4 and s["by_outcome"] == {"answered": 3, "refused_by_model": 1} and s["answered_share"] == 0.75
    assert s["answered"]["tokens_in"] == 3000 and s["answered"]["cost_usd"] == pytest.approx(0.003)
    assert s["answered"]["p50_ms"] == pytest.approx(2000)
    assert trace.summary(conn, timedelta(days=0.0001) - timedelta(days=1))["answered_share"] is None


def test_purge_deletes_only_traces_past_their_expiry(conn):
    trace.record(conn, make(question="old"))
    trace.record(conn, make(question="new"))
    conn.execute("UPDATE query_traces SET expires_at = now() - interval '1 day' WHERE question = 'old'")
    assert trace.expired(conn) == 1
    assert trace.purge(conn) == 1
    assert [r[0] for r in conn.execute("SELECT question FROM query_traces").fetchall()] == ["new"]
    assert trace.purge(conn) == 0


def request_id(sampled: bool, taken: set[str] = frozenset()) -> str:
    """A request id that is in the 1-in-20 sample (or not)."""
    while (candidate := trace.new_request_id()) in taken or trace.in_sample(candidate) != sampled:
        pass
    return candidate


def old(conn, request_id_, days=8):
    conn.execute("UPDATE query_traces SET created_at = now() - make_interval(days => %s) WHERE request_id = %s", (days, request_id_))
    conn.commit()


def test_the_sample_is_chosen_the_same_way_in_python_and_in_sql(conn):
    ids = [f"request-{i}" for i in range(200)]  # fixed ids: the test gives the same result every time
    in_sql = [conn.execute("SELECT (('x' || substr(md5(%s), 1, 8))::bit(32)::bigint %% 20) = 0", (i,)).fetchone()[0] for i in ids]
    assert in_sql == [trace.in_sample(i) for i in ids] and any(in_sql) and not all(in_sql)


def test_scrub_erases_the_text_of_old_ordinary_requests_and_keeps_failures_votes_comments_and_the_sample(conn):
    rows = {  # name: (outcome, sampled, vote, comment, age in days)
        "ordinary": ("answered", False, None, None, 8), "cached": ("cache_hit", False, None, None, 8),
        "limited": ("rate_limited", False, None, None, 8),
        "failure": ("refused_by_model", False, None, None, 8), "thumb_up": ("answered", False, 1, None, 8),
        "thumb_down": ("answered", False, -1, None, 8), "comment": ("answered", False, 1, "merci", 8),
        "sample": ("answered", True, None, None, 8), "young": ("answered", False, None, None, 2),
    }
    ids = {}
    for name, (outcome, sampled, vote, comment, days) in rows.items():
        ids[name] = request_id(sampled, set(ids.values()))
        trace.record(conn, make(outcome, request_id=ids[name], question=f"question {name}", answer="réponse", client_hash="c1"))
        if vote:
            trace.set_feedback(conn, ids[name], vote, comment)
        old(conn, ids[name], days)
    assert trace.erasable(conn) == 3
    assert trace.scrub(conn) == 3
    state = {name: conn.execute("SELECT question, answer, question_sha256, client_hash, erased_at IS NOT NULL FROM query_traces "
                                "WHERE request_id = %s", (i,)).fetchone() for name, i in ids.items()}
    for name in ("ordinary", "cached", "limited"):
        assert state[name] == ("", None, None, None, True), name
    for name in ("failure", "thumb_up", "thumb_down", "comment", "sample", "young"):
        question, answer, digest, client, erased = state[name]
        assert question == f"question {name}" and answer == "réponse" and digest and client == "c1" and not erased, name
    assert trace.scrub(conn) == 0 and trace.erasable(conn) == 0  # nothing more to erase, and the rows are counted once
    assert trace.summary(conn, timedelta(days=30))["requests"] == len(rows)  # the statistics do not lose a request


def test_scrub_edges_the_exact_cutoff_search_rows_a_sample_of_all_and_a_sample_of_none(conn):
    now = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
    rows = {"at_the_cutoff": 7.0, "just_older": 7.001, "just_younger": 6.999}
    ids = {}
    for name, days in rows.items():
        t = make(request_id=request_id(False), question=name)
        ids[name] = t.request_id
        trace.record(conn, t)
        conn.execute("UPDATE query_traces SET created_at = %s WHERE request_id = %s", (now - timedelta(days=days), t.request_id))
    search = make(mode="search", request_id=request_id(False), question="search text", answer=None)
    trace.record(conn, search)
    conn.execute("UPDATE query_traces SET created_at = %s WHERE request_id = %s", (now - timedelta(days=9), search.request_id))
    conn.commit()
    assert trace.erasable(conn, now) == 2  # the row exactly at the cutoff is kept: the rule is "older than"
    assert trace.scrub(conn, now) == 2
    erased = {name: conn.execute("SELECT erased_at IS NOT NULL FROM query_traces WHERE request_id = %s", (i,)).fetchone()[0]
              for name, i in ids.items()}
    assert erased == {"at_the_cutoff": False, "just_older": True, "just_younger": False}
    assert conn.execute("SELECT count(*) FROM query_traces WHERE mode = 'search' AND question = ''").fetchone()[0] == 1  # search rows too
    assert trace.scrub(conn, now, every=1) == 0 and trace.erasable(conn, now, every=1) == 0  # every=1: everyone is in the sample


def test_with_a_sample_of_one_nothing_is_erased_and_with_a_huge_one_almost_nothing_is_kept(conn):
    ids = [request_id(False) for _ in range(3)]
    for i in ids:
        trace.record(conn, make(request_id=i))
        old(conn, i, 10)
    assert trace.erasable(conn, every=1) == 0
    assert trace.erasable(conn, every=10**9) == 3


def test_a_row_with_an_empty_comment_string_counts_as_a_comment_and_keeps_its_text(conn):
    t = make(request_id=request_id(False))
    trace.record(conn, t)
    conn.execute("UPDATE query_traces SET feedback_comment = '' WHERE request_id = %s", (t.request_id,))
    old(conn, t.request_id)
    assert trace.erasable(conn) == 0  # a stored comment, even empty, is a trace of a human act: kept until it expires


def test_the_purge_deletes_an_erased_row_when_it_expires(conn):
    t = make(request_id=request_id(False))
    trace.record(conn, t)
    old(conn, t.request_id, 10)
    trace.scrub(conn)
    conn.execute("UPDATE query_traces SET expires_at = now() - interval '1 minute' WHERE request_id = %s", (t.request_id,))
    assert trace.purge(conn) == 1 and conn.execute("SELECT count(*) FROM query_traces").fetchone()[0] == 0


def test_the_summary_keeps_translations_apart_from_the_requests(conn):
    trace.record(conn, make("answered", cost_usd=0.0004, total_ms=1500))
    trace.record(conn, make("answered", mode="translate", question="", cost_usd=0.0002))
    s = trace.summary(conn, timedelta(days=1))
    assert s["requests"] == 1 and s["by_outcome"] == {"answered": 1} and s["answered"]["cost_usd"] == pytest.approx(0.0004)
    assert s["translations"] == {"n": 1, "cost_usd": pytest.approx(0.0002)}


def test_a_vote_records_when_it_came_and_a_late_vote_on_an_erased_request_is_kept_without_text(conn):
    t = make(request_id=request_id(False))
    trace.record(conn, t)
    old(conn, t.request_id)
    trace.scrub(conn)
    assert trace.set_feedback(conn, t.request_id, -1, "faux", "wrong_answer")
    assert conn.execute("SELECT question, feedback, feedback_at IS NOT NULL FROM query_traces WHERE request_id = %s",
                        (t.request_id,)).fetchone() == ("", -1, True)


def test_feedback_is_stored_for_a_known_request_and_limited_to_up_or_down(conn):
    t = make()
    trace.record(conn, t)
    assert trace.set_feedback(conn, t.request_id, -1, "wrong article") is True
    assert conn.execute("SELECT feedback, feedback_comment FROM query_traces").fetchone() == (-1, "wrong article")
    assert trace.set_feedback(conn, "unknown", 1) is False
    with pytest.raises(psycopg.errors.CheckViolation):
        trace.set_feedback(conn, t.request_id, 5)


def test_votes_lists_the_thumbs_of_normal_answers_newest_first_and_can_keep_only_the_thumbs_down(conn):
    for request_id, outcome, value, kind in (("a", "answered", 1, None), ("b", "answered", -1, "wrong_citation"),
                                             ("c", "cache_hit", -1, "other")):
        trace.record(conn, make(outcome, request_id=request_id))
        trace.set_feedback(conn, request_id, value, f"comment {request_id}" if kind else None, kind)
    trace.record(conn, make(request_id="d"))  # no vote: not listed
    everything = trace.votes(conn, timedelta(days=1))
    assert [(v["feedback"], v["feedback_kind"], v["outcome"], v["feedback_comment"]) for v in everything] == [
        (-1, "other", "cache_hit", "comment c"), (-1, "wrong_citation", "answered", "comment b"), (1, None, "answered", None)]
    assert [v["feedback"] for v in trace.votes(conn, timedelta(days=1), down_only=True)] == [-1, -1]
    assert len(trace.votes(conn, timedelta(days=1), limit=1)) == 1


def test_export_writes_unreviewed_candidates_and_never_overwrites(conn, tmp_path):
    trace.record(conn, make("refused_weak_retrieval", question="Q1", retrieved=RETRIEVED))
    trace.record(conn, make("answered"))
    out = tmp_path / "candidates.jsonl"
    assert trace.export_candidates(conn, timedelta(days=1), out) == 1
    row = json.loads(out.read_text())
    assert row["question"] == "Q1" and row["retrieved"] == ["L1237-1", "L1237-2"] and row["status"] == "unreviewed"
    with pytest.raises(FileExistsError):
        trace.export_candidates(conn, timedelta(days=1), out)


def test_the_client_hash_changes_with_the_day_and_the_address_and_needs_a_secret(monkeypatch):
    monkeypatch.delenv("TRACE_SECRET", raising=False)
    day = date(2026, 11, 3)
    a = trace.client_hash("203.0.113.5", day, "s3cret")
    assert a == trace.client_hash("203.0.113.5", day, "s3cret") and len(a) == 16 and "203" not in a
    assert a != trace.client_hash("203.0.113.5", date(2026, 11, 4), "s3cret") != trace.client_hash("203.0.113.6", day, "s3cret")
    assert trace.client_hash(None) is None
    with pytest.raises(ValueError, match="TRACE_SECRET"):
        trace.client_hash("203.0.113.5", day)
    monkeypatch.setenv("TRACE_SECRET", "from-env")
    assert trace.client_hash("203.0.113.5", day) == trace.client_hash("203.0.113.5", day, "from-env")


def test_a_log_line_is_json_with_the_request_id_and_never_carries_the_question():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logs.JsonFormatter())
    logger = logging.getLogger("test.trace")
    logger.handlers[:] = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logs.log_event(logger, "answered", request_id="abc", outcome="answered", total_ms=1800)
    line = json.loads(stream.getvalue())
    assert line["event"] == "answered" and line["request_id"] == "abc" and line["total_ms"] == 1800 and line["level"] == "INFO"
    for banned in ("question", "answer", "ip"):
        with pytest.raises(ValueError, match="not allowed"):
            logs.log_event(logger, "x", **{banned: "text"})


def test_the_traces_commands_exist_and_refuse_an_unknown_outcome():
    assert runner.invoke(app, ["traces", "--help"]).exit_code == 0
    result = runner.invoke(app, ["traces", "failures", "--outcome", "nothing"])
    assert result.exit_code != 0 and "unknown outcome" in result.output
