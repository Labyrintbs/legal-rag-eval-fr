from datetime import UTC, datetime, timedelta

import pytest

from legalrag.answering import cache, trace

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
PARTS = {"model": "deepseek-flash", "prompt_id": "answer.v3", "threshold": 0.55, "data_version": "d1", "code_version": "c1"}
REPLY = {"outcome": "answered", "claims": [], "articles": []}


@pytest.fixture(autouse=True)
def clean_tables(conn):
    """put() and record() commit, so each test empties what they wrote."""
    yield
    conn.rollback()
    conn.execute("DELETE FROM answer_cache")
    conn.execute("DELETE FROM query_traces")
    conn.commit()


def key(question="Quelle durée ?", **changes):
    return cache.key_of(question, **(PARTS | changes))


def test_an_english_translation_goes_with_its_reply_and_is_dropped_when_the_reply_is_made_again(conn):
    cache.put(conn, key(), "answered", REPLY, NOW)
    assert cache.reply_and_translation(conn, key(), NOW) == (REPLY, None)
    cache.set_translation(conn, key(), "Four months. [1]")
    assert cache.reply_and_translation(conn, key(), NOW) == (REPLY, "Four months. [1]")
    assert cache.reply_and_translation(conn, key("autre"), NOW) is None
    assert cache.reply_and_translation(conn, key(), NOW + timedelta(days=8)) is None  # expired
    cache.put(conn, key(), "answered", REPLY, NOW)  # a new reply: the old translation no longer fits it
    assert cache.reply_and_translation(conn, key(), NOW) == (REPLY, None)


def test_the_question_is_compared_without_case_and_extra_spaces():
    assert cache.normalise("  Quelle   DURÉE\n?  ") == "quelle durée ?"
    assert key("Quelle durée ?") == key("  QUELLE durée   ? ")


@pytest.mark.parametrize("change", [{"model": "other"}, {"prompt_id": "answer.v4"}, {"threshold": 0.6}, {"data_version": "d2"},
                                    {"code_version": "c2"}])
def test_a_change_of_any_part_of_the_key_gives_another_key(change):
    assert key(**change) != key()


def test_another_question_gives_another_key_and_the_key_hides_the_question():
    assert key("Quelle durée ?") != key("Quelle durée pour un cadre ?")
    assert "durée" not in key() and len(key()) == 64


def test_a_stored_reply_comes_back_and_each_read_adds_a_hit(conn):
    cache.put(conn, key(), "answered", REPLY, NOW)
    assert cache.get(conn, key(), NOW) == REPLY
    assert cache.get(conn, key(), NOW, count=False) == REPLY
    assert conn.execute("SELECT hits FROM answer_cache").fetchone()[0] == 1


def test_a_missing_or_expired_reply_is_a_miss_and_storing_again_resets_the_hits(conn):
    assert cache.get(conn, key(), NOW) is None
    cache.put(conn, key(), "answered", REPLY, NOW)
    assert cache.get(conn, key(), NOW + cache.TTL - timedelta(seconds=1)) == REPLY
    assert cache.get(conn, key(), NOW + cache.TTL) is None
    cache.put(conn, key(), "refused_by_model", {"outcome": "refused_by_model"}, NOW + cache.TTL)
    assert cache.get(conn, key(), NOW + cache.TTL, count=False) == {"outcome": "refused_by_model"}
    assert conn.execute("SELECT hits FROM answer_cache").fetchone()[0] == 0


@pytest.mark.parametrize("outcome", ["llm_error", "rate_limited", "llm_disabled", "refused_weak_retrieval", "parse_error"])
def test_only_the_stable_outcomes_can_be_stored(conn, outcome):
    with pytest.raises(ValueError, match="not cached"):
        cache.put(conn, key(), outcome, REPLY, NOW)


def test_purge_removes_the_expired_entries_and_clear_removes_all(conn):
    cache.put(conn, key("old"), "answered", REPLY, NOW - cache.TTL - timedelta(days=1))
    cache.put(conn, key("new"), "answered", REPLY, NOW)
    assert cache.counts(conn, NOW) == (1, 1)
    assert cache.purge(conn, NOW) == 1 and cache.counts(conn, NOW) == (1, 0)
    assert cache.clear(conn) == 1 and cache.counts(conn, NOW) == (0, 0)


def test_delete_says_whether_there_was_an_entry(conn):
    cache.put(conn, key(), "answered", REPLY, NOW)
    assert cache.delete(conn, key()) is True and cache.delete(conn, key()) is False


def test_a_pinned_entry_does_not_expire_and_pin_keeps_an_existing_entry_in_place(conn):
    cache.put(conn, key("example"), "answered", REPLY, NOW, pinned=True)
    far = NOW + timedelta(days=3650)
    assert cache.get(conn, key("example"), far) == REPLY and cache.purge(conn, far) == 0
    cache.put(conn, key("visitor"), "answered", REPLY, NOW)  # stored after a visitor's question, expires in 7 days
    assert cache.pin(conn, key("visitor"), NOW) is True
    assert cache.get(conn, key("visitor"), far, count=False) == REPLY
    assert cache.pin(conn, key("never asked"), NOW) is False
    cache.put(conn, key("old"), "answered", REPLY, NOW - cache.TTL - timedelta(days=1))
    assert cache.pin(conn, key("old"), NOW) is False  # an expired entry is not brought back


def add_trace(conn, request_id, client, cache_key):
    trace.record(conn, trace.Trace(request_id=request_id, lang="fr", question="q", mode="answer", outcome="answered",
                                   client_hash=client, cache_key=cache_key))


def test_a_vote_removes_the_entry_only_for_the_client_who_got_the_reply(conn):
    cache.put(conn, key(), "answered", REPLY, NOW)
    add_trace(conn, "r1", "alice", key())
    add_trace(conn, "r2", None, key())
    add_trace(conn, "r3", "alice", None)  # a request that has no entry (a search)
    assert cache.drop_for_vote(conn, "r1", "bob") is False  # another client
    assert cache.drop_for_vote(conn, "r2", None) is False  # no known client on either side
    assert cache.drop_for_vote(conn, "r3", "alice") is False
    assert cache.drop_for_vote(conn, "unknown", "alice") is False
    assert cache.counts(conn)[0] == 1
    assert cache.drop_for_vote(conn, "r1", "alice") is True and cache.counts(conn)[0] == 0


def test_a_vote_keeps_a_pinned_entry(conn):
    cache.put(conn, key(), "answered", REPLY, NOW, pinned=True)
    add_trace(conn, "r1", "alice", key())
    assert cache.drop_for_vote(conn, "r1", "alice") is False and cache.counts(conn)[0] == 1


def test_the_data_version_changes_with_the_corpus_and_the_chunking_run(conn):
    conn.execute("INSERT INTO corpus_versions (source_key, source_name, source_url, retrieved_at, file_sha256, row_count, license) "
                 "VALUES ('s', 'n', 'u', now(), 'aaa', 1, 'l')")
    run = ("INSERT INTO chunking_runs (name, header_style, max_tokens, split_rule, tokenizer, code_version, params) "
           "VALUES ('default', 'x', 1, 'r', 't', 'v', %s)")
    conn.execute(run, ('{"k": 1}',))
    first = cache.data_version(conn, "default")
    assert first == cache.data_version(conn, "default") and len(first) == 12
    conn.execute("UPDATE corpus_versions SET file_sha256 = 'bbb'")
    second = cache.data_version(conn, "default")
    conn.execute("UPDATE chunking_runs SET params = '{\"k\": 2}'")
    assert len({first, second, cache.data_version(conn, "default")}) == 3
