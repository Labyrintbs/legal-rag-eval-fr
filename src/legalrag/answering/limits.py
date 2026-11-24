"""Rate limits and the kill switch (step 0d, decisions 13 to 15). Before a model call, `decide` counts the
requests in `query_traces` and reads the `llm_enabled` flag; search is never limited. The service must trace
every request, limited ones included, for the counts to be right. A reply from the answer cache (step 0f, decision 4)
is checked by `decide_cached`: only its own minute counter applies.
"""

import threading
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import psycopg

# requests that did not reach the model cost nothing and do not count; a reply from the answer cache has its own
# minute counter (`per_minute_cached`) and does not use the model allowance or the day's quota
NOT_COUNTED = ("rate_limited", "llm_disabled", "refused_weak_retrieval", "cache_hit")
COUNTED = ("SELECT count(*), min(created_at) FROM query_traces WHERE client_hash IS NOT DISTINCT FROM %s::text "
           "AND mode = 'answer' AND outcome <> ALL(%s) AND created_at >= %s")
COUNTED_CACHED = ("SELECT count(*), min(created_at) FROM query_traces WHERE client_hash IS NOT DISTINCT FROM %s::text "
                  "AND mode = 'answer' AND outcome = 'cache_hit' AND created_at >= %s")


@dataclass(frozen=True)
class Settings:
    per_minute: int = 5  # per client: replies that called the model
    per_day: int = 30  # per client, UTC day, replies that called the model
    per_minute_cached: int = 30  # per client: replies from the cache (they cost no model call); a guess, untested
    translate_per_minute: int = 5  # per client: new translations, of a question or of an answer (each is a model call); the user's choice
    translate_per_day: int = 30  # per client, UTC day: the same count as the answers; a first value, to review
    cost_per_day_usd: float = 0.10  # whole service, UTC day


@dataclass(frozen=True)
class Decision:
    allowed: bool
    outcome: str | None = None  # rate_limited or llm_disabled when not allowed
    reason: str | None = None
    status: int = 200  # 429 for a client limit, 503 for the cost cap or the switch
    retry_after: int | None = None  # seconds


ALLOWED = Decision(True)


def llm_enabled(conn: psycopg.Connection) -> bool:
    """False when the flag is off or missing: without the flag the service does not spend money."""
    row = conn.execute("SELECT value FROM service_flags WHERE name = 'llm_enabled'").fetchone()
    return row is not None and row[0]


def set_llm_enabled(conn: psycopg.Connection, value: bool) -> None:
    conn.execute("UPDATE service_flags SET value = %s, changed_at = now() WHERE name = 'llm_enabled'", (value,))
    conn.commit()


def _seconds_until(moment: datetime, now: datetime) -> int:
    return max(1, int((moment - now).total_seconds()) + 1)


def _too_many(count: int, oldest: datetime | None, limit: int, what: str, now: datetime) -> Decision | None:
    if count < limit:
        return None
    wait = _seconds_until(oldest + timedelta(minutes=1), now)
    return Decision(False, "rate_limited", f"more than {limit} {what} a minute, retry in {wait} s", 429, wait)


def _minute_limit(conn: psycopg.Connection, client: str | None, settings: Settings, now: datetime) -> Decision | None:
    count, oldest = conn.execute(COUNTED, (client, list(NOT_COUNTED), now - timedelta(minutes=1))).fetchone()
    return _too_many(count, oldest, settings.per_minute, "questions", now)


def _cached_minute_limit(conn: psycopg.Connection, client: str | None, settings: Settings, now: datetime) -> Decision | None:
    count, oldest = conn.execute(COUNTED_CACHED, (client, now - timedelta(minutes=1))).fetchone()
    return _too_many(count, oldest, settings.per_minute_cached, "cached replies", now)


def decide(conn: psycopg.Connection, client: str | None, settings: Settings, now: datetime | None = None,
           per_client: bool = True) -> Decision:
    """Whether this client may have a written answer now. Clients with no address share one count. `per_client` False
    leaves out the client limits and keeps the switch and the daily budget: the cache warm-up has no client."""
    now = now or datetime.now(UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    next_day = _seconds_until(day_start + timedelta(days=1), now)
    if not llm_enabled(conn):
        return Decision(False, "llm_disabled", "written answers are switched off", 503)
    spent = conn.execute("SELECT coalesce(sum(cost_usd), 0)::float FROM query_traces WHERE created_at >= %s",
                         (day_start,)).fetchone()[0]
    if spent >= settings.cost_per_day_usd:
        return Decision(False, "rate_limited", "the daily budget of the service is used up", 503, next_day)
    if not per_client:
        return ALLOWED
    if blocked := _minute_limit(conn, client, settings, now):
        return blocked
    in_day = conn.execute(COUNTED, (client, list(NOT_COUNTED), day_start)).fetchone()[0]
    if in_day >= settings.per_day:
        return Decision(False, "rate_limited", f"more than {settings.per_day} questions today", 429, next_day)
    return ALLOWED


COUNTED_TRANSLATIONS = ("SELECT count(*), min(created_at) FROM query_traces WHERE client_hash IS NOT DISTINCT FROM %s::text "
                        "AND mode = 'translate' AND created_at >= %s")


def decide_translation(conn: psycopg.Connection, client: str | None, settings: Settings, now: datetime | None = None) -> Decision:
    """Whether this client may have a new translation now (of a question before the search, or of an answer). It is a model
    call: it needs the switch and the day's budget like an answer, and it has counters of its own, per minute and per day,
    because it is traced apart (mode "translate"), whatever the outcome of the answer that follows."""
    now = now or datetime.now(UTC)
    base = decide(conn, client, settings, now, per_client=False)
    if not base.allowed:
        return base
    count, oldest = conn.execute(COUNTED_TRANSLATIONS, (client, now - timedelta(minutes=1))).fetchone()
    if blocked := _too_many(count, oldest, settings.translate_per_minute, "translations", now):
        return blocked
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    in_day = conn.execute(COUNTED_TRANSLATIONS, (client, day_start)).fetchone()[0]
    if in_day >= settings.translate_per_day:
        return Decision(False, "rate_limited", f"more than {settings.translate_per_day} translations today", 429,
                        _seconds_until(day_start + timedelta(days=1), now))
    return ALLOWED


class Overloaded(Exception):
    """Too many searches are waiting for the processor: the request is refused at once (a 503) instead of waiting for minutes."""


def decide_cached(conn: psycopg.Connection, client: str | None, settings: Settings, now: datetime | None = None) -> Decision:
    """Whether this client may have a reply from the cache now. It costs nothing, so the switch and the daily budget do
    not apply (cached replies keep working when the cap is used up), and the model allowance is not used: only the
    client's own minute counter for cached replies applies."""
    return _cached_minute_limit(conn, client, settings, now or datetime.now(UTC)) or ALLOWED


class Limits:
    """`decide` with its own connection and settings, for the answer engine."""

    def __init__(self, connect: Callable[[], psycopg.Connection], settings: Settings | None = None) -> None:
        self.connect, self.settings = connect, settings or Settings()
        self.busy: set[str] = set()  # visitors with a request in progress (the service runs one process)
        self.busy_lock = threading.Lock()
        self.flights: dict[str, tuple[threading.Lock, int]] = {}  # questions being answered, with the number of requests on each
        self.flight_lock = threading.Lock()

    def begin(self, client: str | None) -> bool:
        """One request at a time for a visitor. The counts above are written after the model call, so requests sent in a
        burst would all be counted before any was recorded and all pass; this closes it. False: one is already in progress."""
        with self.busy_lock:
            if (client or "-") in self.busy:
                return False
            self.busy.add(client or "-")
            return True

    def end(self, client: str | None) -> None:
        with self.busy_lock:
            self.busy.discard(client or "-")

    @contextmanager
    def single_flight(self, key: str):
        """The same question asked by several visitors at the same time is answered once: the others wait for the first, then
        find its answer in the memory instead of each calling the model. The lock of a key is dropped when nobody uses it."""
        with self.flight_lock:
            lock, users = self.flights.get(key, (threading.Lock(), 0))
            self.flights[key] = (lock, users + 1)
        try:
            with lock:
                yield
        finally:
            with self.flight_lock:
                lock, users = self.flights[key]
                if users == 1:
                    del self.flights[key]
                else:
                    self.flights[key] = (lock, users - 1)

    def check_translation(self, client: str | None) -> Decision:
        with self.connect() as conn:
            return decide_translation(conn, client, self.settings)

    def check(self, client: str | None, per_client: bool = True) -> Decision:
        with self.connect() as conn:
            return decide(conn, client, self.settings, per_client=per_client)

    def check_cached(self, client: str | None) -> Decision:
        with self.connect() as conn:
            return decide_cached(conn, client, self.settings)
