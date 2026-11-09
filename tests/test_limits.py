from datetime import UTC, datetime, timedelta

import pytest
from conftest import with_database

from legalrag import db, limits, trace
from legalrag.config import database_url

NOW = datetime(2026, 11, 9, 12, 0, 30, tzinfo=UTC)
SETTINGS = limits.Settings(per_minute=5, per_day=30, cost_per_day_usd=0.10)


@pytest.fixture(autouse=True)
def clean_tables(conn):
    """record() commits, so each test empties the table and turns the switch back on."""
    yield
    conn.rollback()
    conn.execute("DELETE FROM query_traces")
    conn.execute("UPDATE service_flags SET value = true WHERE name = 'llm_enabled'")
    conn.commit()


def add(conn, n=1, client="c1", outcome="answered", ago=timedelta(seconds=10), **changes):
    """n traces made `ago` before NOW."""
    for _ in range(n):
        base = {"request_id": trace.new_request_id(), "lang": "fr", "question": "q", "mode": "answer", "outcome": outcome,
                "client_hash": client}
        trace_id = trace.record(conn, trace.Trace(**(base | changes)))
        conn.execute("UPDATE query_traces SET created_at = %s WHERE id = %s", (NOW - ago, trace_id))
    conn.commit()


def decide(conn, client="c1"):
    return limits.decide(conn, client, SETTINGS, NOW)


def test_a_new_client_is_allowed(conn):
    assert decide(conn) == limits.ALLOWED


def test_the_switch_off_blocks_the_model_with_503_and_a_missing_flag_counts_as_off(conn):
    limits.set_llm_enabled(conn, False)
    verdict = decide(conn)
    assert (verdict.allowed, verdict.outcome, verdict.status) == (False, "llm_disabled", 503)
    limits.set_llm_enabled(conn, True)
    assert decide(conn).allowed
    conn.execute("DELETE FROM service_flags")
    assert not limits.llm_enabled(conn)
    conn.rollback()


def test_the_fifth_question_of_a_minute_is_allowed_and_the_sixth_is_not(conn):
    add(conn, 4)
    assert decide(conn).allowed
    add(conn, 1)
    verdict = decide(conn)
    assert (verdict.allowed, verdict.outcome, verdict.status) == (False, "rate_limited", 429)
    assert 1 <= verdict.retry_after <= 60 and "minute" in verdict.reason


def test_the_wait_ends_when_the_oldest_question_of_the_minute_leaves_the_window(conn):
    add(conn, 1, ago=timedelta(seconds=50))
    add(conn, 4, ago=timedelta(seconds=5))
    assert decide(conn).retry_after == 11  # the 50 s old one leaves the window in 10 s


def test_questions_older_than_a_minute_count_for_the_day_only(conn):
    add(conn, 30, ago=timedelta(minutes=5))
    verdict = decide(conn)
    assert (verdict.status, verdict.retry_after) == (429, int((datetime(2026, 11, 10, tzinfo=UTC) - NOW).total_seconds()) + 1)
    assert "today" in verdict.reason
    conn.execute("DELETE FROM query_traces")
    add(conn, 29, ago=timedelta(minutes=5))
    assert decide(conn).allowed


def test_yesterday_and_other_clients_do_not_count(conn):
    add(conn, 30, ago=timedelta(hours=13))  # 23:00 yesterday
    add(conn, 30, client="c2", ago=timedelta(minutes=5))
    assert decide(conn).allowed
    assert not decide(conn, "c2").allowed


def test_requests_that_did_not_reach_the_model_do_not_count(conn):
    for outcome in limits.NOT_COUNTED:
        add(conn, 10, outcome=outcome)
    add(conn, 10, mode="search")
    assert decide(conn).allowed


def test_refused_and_failed_model_calls_count(conn):
    for outcome in ("refused_by_model", "invalid_citation", "parse_error", "llm_error"):
        add(conn, 1, outcome=outcome)
    add(conn, 1)
    assert not decide(conn).allowed


def test_requests_with_no_address_share_one_count(conn):
    add(conn, 5, client=None)
    assert not decide(conn, None).allowed
    assert decide(conn, "c1").allowed


def test_the_daily_budget_stops_every_client_with_503_until_midnight(conn):
    add(conn, 2, client="a", cost_usd=0.05)
    verdict = decide(conn, "someone-new")
    assert (verdict.allowed, verdict.outcome, verdict.status) == (False, "rate_limited", 503)
    assert verdict.retry_after == int((datetime(2026, 11, 10, tzinfo=UTC) - NOW).total_seconds()) + 1
    conn.execute("DELETE FROM query_traces")
    add(conn, 2, client="a", cost_usd=0.0499, ago=timedelta(hours=13))  # yesterday
    assert decide(conn, "someone-new").allowed


def test_limits_wrapper_opens_its_own_connection(conn, database_name):
    gate = limits.Limits(lambda: db.connect(with_database(database_url(), database_name)), SETTINGS)
    assert gate.check("c1").allowed
