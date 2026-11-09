"""Rate limits and the kill switch (step 0d, decisions 13 to 15). Before a model call, `decide` counts the
requests in `query_traces` and reads the `llm_enabled` flag; search is never limited. The service must trace
every request, limited ones included, for the counts to be right.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import psycopg

# requests that did not reach the model cost nothing and do not count
NOT_COUNTED = ("rate_limited", "llm_disabled", "refused_weak_retrieval")


@dataclass(frozen=True)
class Settings:
    per_minute: int = 5  # per client
    per_day: int = 30  # per client, UTC day
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


def decide(conn: psycopg.Connection, client: str | None, settings: Settings, now: datetime | None = None) -> Decision:
    """Whether this client may have a written answer now. Clients with no address share one count."""
    now = now or datetime.now(UTC)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    next_day = _seconds_until(day_start + timedelta(days=1), now)
    if not llm_enabled(conn):
        return Decision(False, "llm_disabled", "written answers are switched off", 503)
    spent = conn.execute("SELECT coalesce(sum(cost_usd), 0)::float FROM query_traces WHERE created_at >= %s",
                         (day_start,)).fetchone()[0]
    if spent >= settings.cost_per_day_usd:
        return Decision(False, "rate_limited", "the daily budget of the service is used up", 503, next_day)
    counted = ("SELECT count(*), min(created_at) FROM query_traces WHERE client_hash IS NOT DISTINCT FROM %s::text "
               "AND mode = 'answer' AND outcome <> ALL(%s) AND created_at >= %s")
    minute_start = now - timedelta(minutes=1)
    in_minute, oldest = conn.execute(counted, (client, list(NOT_COUNTED), minute_start)).fetchone()
    if in_minute >= settings.per_minute:
        wait = _seconds_until(oldest + timedelta(minutes=1), now)
        return Decision(False, "rate_limited", f"more than {settings.per_minute} questions a minute, retry in {wait} s", 429, wait)
    in_day = conn.execute(counted, (client, list(NOT_COUNTED), day_start)).fetchone()[0]
    if in_day >= settings.per_day:
        return Decision(False, "rate_limited", f"more than {settings.per_day} questions today", 429, next_day)
    return ALLOWED


class Limits:
    """`decide` with its own connection and settings, for the answer engine."""

    def __init__(self, connect: Callable[[], psycopg.Connection], settings: Settings | None = None) -> None:
        self.connect, self.settings = connect, settings or Settings()

    def check(self, client: str | None) -> Decision:
        with self.connect() as conn:
            return decide(conn, client, self.settings)
