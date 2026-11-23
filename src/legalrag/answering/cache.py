"""The answer cache (step 0f, decision 4 of docs/decisions/0008): the finished reply of a question, found again by an
exact match on the normalised question and on everything that changes an answer. Only a hash of the question is
stored, never its text: a visitor may type personal data. Only the replies that cost a model call and are stable
are kept (`CACHEABLE`); an error, a limit or the switch-off is never cached.
"""

import hashlib
from datetime import UTC, datetime, timedelta

import psycopg
from psycopg.types.json import Jsonb

TTL = timedelta(days=7)  # a guess, untested: the version parts of the key already stop a stale reply after a change
PINNED_EXPIRY = datetime(9999, 1, 1, tzinfo=UTC)  # a pinned entry stays until `cache clear` or a new version of the key
CACHEABLE = ("answered", "refused_by_model")


def normalise(question: str) -> str:
    """"  Quelle DURÉE ?  " and "quelle durée ?" are the same question."""
    return " ".join(question.lower().split())


def key_of(question: str, *, model: str, prompt_id: str, threshold: float, data_version: str, code_version: str) -> str:
    """A change of any part (model, prompt, search threshold, data, code) gives a new key, so an old reply is never served for new settings."""
    parts = (normalise(question), model, prompt_id, f"{threshold:.4f}", data_version, code_version)
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def data_version(conn: psycopg.Connection, run_name: str) -> str:
    """A short hash of what the answers are made from: the corpus files and the settings of the chunking run."""
    sources = conn.execute("SELECT source_key, file_sha256 FROM corpus_versions ORDER BY source_key, file_sha256").fetchall()
    run = conn.execute("SELECT params::text, tokenizer FROM chunking_runs WHERE name = %s", (run_name,)).fetchone()
    return hashlib.sha256(repr((sources, run)).encode()).hexdigest()[:12]


def get(conn: psycopg.Connection, key: str, now: datetime | None = None, count: bool = True) -> dict | None:
    """The stored reply, or none when there is none or it has expired. `count` False does not add a hit."""
    row = conn.execute("UPDATE answer_cache SET hits = hits + %s WHERE key = %s AND expires_at > %s RETURNING reply",
                       (1 if count else 0, key, now or datetime.now(UTC))).fetchone()
    conn.commit()
    return row[0] if row else None


def put(conn: psycopg.Connection, key: str, outcome: str, reply: dict, now: datetime | None = None,
        pinned: bool = False) -> None:
    """Store a reply. A pinned entry (an example question of the demo) does not expire."""
    if outcome not in CACHEABLE:
        raise ValueError(f"{outcome!r} is not cached")
    now = now or datetime.now(UTC)
    conn.execute(
        "INSERT INTO answer_cache (key, reply, outcome, created_at, expires_at, pinned) VALUES (%s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (key) DO UPDATE SET reply = EXCLUDED.reply, outcome = EXCLUDED.outcome, "
        "created_at = EXCLUDED.created_at, expires_at = EXCLUDED.expires_at, pinned = EXCLUDED.pinned, hits = 0",
        (key, Jsonb(reply), outcome, now, PINNED_EXPIRY if pinned else now + TTL, pinned))
    conn.commit()


def pin(conn: psycopg.Connection, key: str, now: datetime | None = None) -> bool:
    """Pin the entry (it then does not expire); false when there is no valid entry. The warm-up pins an example that a
    visitor had already caused to be stored."""
    done = conn.execute("UPDATE answer_cache SET pinned = true, expires_at = %s WHERE key = %s AND expires_at > %s",
                        (PINNED_EXPIRY, key, now or datetime.now(UTC))).rowcount == 1
    conn.commit()
    return done


def delete(conn: psycopg.Connection, key: str) -> bool:
    done = conn.execute("DELETE FROM answer_cache WHERE key = %s", (key,)).rowcount == 1
    conn.commit()
    return done


def drop_for_vote(conn: psycopg.Connection, request_id: str, client: str | None) -> bool:
    """A thumbs-down removes the entry that served the request, but only when the voter is the client who got that
    reply (otherwise a stranger could clear entries and make the service pay for new answers) and the entry is not
    pinned (the examples of the demo stay until the owner decides; the vote is kept on the trace either way)."""
    row = conn.execute("SELECT cache_key, client_hash FROM query_traces WHERE request_id = %s", (request_id,)).fetchone()
    if not row or not row[0] or client is None or row[1] != client:
        return False
    removed = conn.execute("DELETE FROM answer_cache WHERE key = %s AND NOT pinned", (row[0],)).rowcount == 1
    conn.commit()
    return removed


def counts(conn: psycopg.Connection, now: datetime | None = None) -> tuple[int, int]:
    """(entries still valid, entries expired and not yet purged)."""
    live, expired = conn.execute(
        "SELECT count(*) FILTER (WHERE expires_at > %(now)s), count(*) FILTER (WHERE expires_at <= %(now)s) FROM answer_cache",
        {"now": now or datetime.now(UTC)}).fetchone()
    return live, expired


def purge(conn: psycopg.Connection, now: datetime | None = None) -> int:
    """Delete the expired entries; return how many."""
    removed = conn.execute("DELETE FROM answer_cache WHERE expires_at <= %s", (now or datetime.now(UTC),)).rowcount
    conn.commit()
    return removed


def clear(conn: psycopg.Connection) -> int:
    """Delete every entry; return how many."""
    removed = conn.execute("DELETE FROM answer_cache").rowcount
    conn.commit()
    return removed
