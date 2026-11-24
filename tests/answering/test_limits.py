import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
from conftest import with_database

from legalrag.answering import limits, trace
from legalrag.index import db
from legalrag.index.config import database_url

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


def test_cached_replies_use_neither_the_model_allowance_of_the_minute_nor_the_day_quota(conn):
    add(conn, 30, outcome="cache_hit", ago=timedelta(minutes=5))  # a day's quota of cached replies...
    add(conn, 30, outcome="cache_hit")  # ...and a minute's worth of them
    assert decide(conn).allowed  # a model answer is still allowed


def test_a_cached_reply_has_its_own_minute_counter_and_needs_neither_the_switch_nor_the_budget(conn):
    assert limits.decide_cached(conn, "c1", SETTINGS, NOW) == limits.ALLOWED
    limits.set_llm_enabled(conn, False)
    add(conn, 2, client="a", cost_usd=0.05)  # the day's budget is used up
    assert limits.decide_cached(conn, "someone-new", SETTINGS, NOW).allowed
    add(conn, 5, client="c1")  # a minute of model answers does not block a cached reply
    assert limits.decide_cached(conn, "c1", SETTINGS, NOW).allowed
    add(conn, 29, client="c1", outcome="cache_hit")
    assert limits.decide_cached(conn, "c1", SETTINGS, NOW).allowed
    add(conn, 1, client="c1", outcome="cache_hit")
    verdict = limits.decide_cached(conn, "c1", SETTINGS, NOW)
    assert (verdict.allowed, verdict.outcome, verdict.status) == (False, "rate_limited", 429)
    assert "cached replies" in verdict.reason and 1 <= verdict.retry_after <= 60


def test_the_warm_up_decision_keeps_the_switch_and_the_budget_but_not_the_client_limits(conn):
    add(conn, 30, client=None)  # would block a client with no address
    assert limits.decide(conn, None, SETTINGS, NOW, per_client=False).allowed
    limits.set_llm_enabled(conn, False)
    assert limits.decide(conn, None, SETTINGS, NOW, per_client=False).outcome == "llm_disabled"
    limits.set_llm_enabled(conn, True)
    add(conn, 2, client="a", cost_usd=0.05)
    assert limits.decide(conn, None, SETTINGS, NOW, per_client=False).status == 503


def add_translation(conn, n=1, client="c1", ago=timedelta(seconds=10), cost=0.0002, outcome="answered"):
    add(conn, n, client=client, outcome=outcome, ago=ago, mode="translate", question="", cost_usd=cost)


def translation(conn, client="c1"):
    return limits.decide_translation(conn, client, SETTINGS, NOW)


def test_a_translation_has_its_own_minute_counter_and_the_sixth_is_refused(conn):
    add_translation(conn, 4)
    assert translation(conn).allowed
    add_translation(conn, 1)
    verdict = translation(conn)
    assert (verdict.allowed, verdict.outcome, verdict.status) == (False, "rate_limited", 429)
    assert 1 <= verdict.retry_after <= 60 and "translations" in verdict.reason
    assert translation(conn, "c2").allowed  # another visitor


def test_a_translation_has_a_daily_counter_too_and_old_ones_count_for_the_day_only(conn):
    add_translation(conn, 29, ago=timedelta(minutes=5))
    assert translation(conn).allowed
    add_translation(conn, 1, ago=timedelta(minutes=5))
    verdict = translation(conn)
    assert (verdict.status, verdict.outcome) == (429, "rate_limited") and "today" in verdict.reason
    assert verdict.retry_after == int((datetime(2026, 11, 10, tzinfo=UTC) - NOW).total_seconds()) + 1
    conn.execute("DELETE FROM query_traces")
    add_translation(conn, 40, ago=timedelta(hours=13))  # yesterday
    assert translation(conn).allowed


def test_translations_and_answers_do_not_use_each_others_allowances(conn):
    add_translation(conn, 10)
    assert decide(conn).allowed  # ten translations are no answer of the minute
    conn.execute("DELETE FROM query_traces")
    add(conn, 5)
    assert not decide(conn).allowed and translation(conn).allowed  # five answers do not block a translation


def test_a_translation_needs_the_switch_and_the_budget_and_its_cost_counts_in_the_budget(conn):
    add_translation(conn, 2, client="a", cost=0.05)  # the day's budget is used up by translations alone
    verdict = translation(conn, "someone-new")
    assert (verdict.allowed, verdict.status) == (False, 503)
    assert decide(conn, "someone-new").status == 503  # and answers are stopped too
    conn.execute("DELETE FROM query_traces")
    limits.set_llm_enabled(conn, False)
    assert translation(conn).outcome == "llm_disabled"


def test_a_failed_translation_counts_even_without_a_known_cost(conn):
    add_translation(conn, 5, cost=None, outcome="llm_error")
    assert not translation(conn).allowed  # the call was made: it uses a place


def test_one_request_at_a_time_per_visitor_and_the_slot_is_freed(conn):
    gate = limits.Limits(lambda: None)
    assert gate.begin("a") and not gate.begin("a") and gate.begin("b") and gate.begin(None) and not gate.begin(None)
    gate.end("a")
    assert gate.begin("a")
    gate.end("zz")  # ending a slot that is not taken does nothing
    assert gate.busy == {"a", "b", "-"}


def test_the_lock_of_a_question_is_dropped_when_nobody_uses_it_and_is_held_by_one_at_a_time():
    gate = limits.Limits(lambda: None)
    order = []

    def use(name):
        with gate.single_flight("same question"):
            order.append(("in", name))
            time.sleep(0.05)
            order.append(("out", name))

    threads = [threading.Thread(target=use, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert [kind for kind, _ in order] == ["in", "out"] * 4  # never two inside at the same time
    assert gate.flights == {}  # nothing is left behind
    with gate.single_flight("a"), gate.single_flight("b"):  # other questions do not wait for each other
        assert set(gate.flights) == {"a", "b"}
    assert gate.flights == {}


def test_limits_wrapper_opens_its_own_connection(conn, database_name):
    gate = limits.Limits(lambda: db.connect(with_database(database_url(), database_name)), SETTINGS)
    assert gate.check("c1").allowed
