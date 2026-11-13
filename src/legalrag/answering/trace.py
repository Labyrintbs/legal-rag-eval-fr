"""Tracing (step 0d, decision 8): one row of `query_traces` per request to the service, and what is asked of
those rows: the failures, a summary, purging after 30 days, and an export of candidates for the eval set.
"""

import hashlib
import hmac
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

OUTCOMES = (
    "answered", "refused_weak_retrieval", "refused_by_model", "invalid_citation",
    "parse_error", "llm_error", "rate_limited", "llm_disabled",
)  # the same list as the CHECK of migration 0003
FEEDBACK_KINDS = ("wrong_answer", "wrong_citation", "missing_article", "other")  # the CHECK of migration 0005
FAILURES = ("refused_weak_retrieval", "refused_by_model", "invalid_citation", "parse_error", "llm_error")
# rate_limited and llm_disabled say how the service was run, not that the system could not answer


@dataclass
class Trace:
    request_id: str
    lang: str
    question: str
    mode: str  # answer or search
    outcome: str
    client_hash: str | None = None
    refusal_reason: str | None = None
    error: str | None = None
    retrieved: list[dict] = field(default_factory=list)  # [{"label", "chunk_index", "score"}], best first
    cited: list[dict] = field(default_factory=list)  # [{"label", "chunk_index", "unit"}]
    answer: str | None = None
    model: str | None = None
    prompt_id: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    tokens_cached: int | None = None
    cost_usd: float | None = None
    retrieval_ms: int | None = None
    llm_ms: int | None = None
    total_ms: int | None = None
    code_version: str | None = None
    data_version: str | None = None


def new_request_id() -> str:
    return uuid.uuid4().hex


def client_hash(address: str | None, day: date | None = None, secret: str | None = None) -> str | None:
    """A short keyed hash of the client address that changes every day, so a client cannot be followed over
    days and the raw address is never stored. The secret comes from TRACE_SECRET; there is no default."""
    if address is None:
        return None
    secret = secret or os.environ.get("TRACE_SECRET")
    if not secret:
        raise ValueError("TRACE_SECRET is not set")
    day = day or datetime.now(UTC).date()
    return hmac.new(secret.encode(), f"{day.isoformat()}|{address}".encode(), hashlib.sha256).hexdigest()[:16]


def _scores(retrieved: list[dict]) -> tuple[float | None, float | None]:
    """The best score and its gap to the second, from the scores of the retrieved articles."""
    scores = [r["score"] for r in retrieved if r.get("score") is not None]
    return (scores[0], scores[0] - scores[1]) if len(scores) > 1 else (scores[0] if scores else None, None)


INSERT = (
    "INSERT INTO query_traces (request_id, lang, question, question_sha256, client_hash, mode, outcome, "
    "refusal_reason, error, retrieved, top_score, score_gap, cited, answer, model, prompt_id, tokens_in, "
    "tokens_out, tokens_cached, cost_usd, retrieval_ms, llm_ms, total_ms, code_version, data_version) "
    "VALUES (%(request_id)s, %(lang)s, %(question)s, %(question_sha256)s, %(client_hash)s, %(mode)s, %(outcome)s, "
    "%(refusal_reason)s, %(error)s, %(retrieved)s, %(top_score)s, %(score_gap)s, %(cited)s, %(answer)s, %(model)s, "
    "%(prompt_id)s, %(tokens_in)s, %(tokens_out)s, %(tokens_cached)s, %(cost_usd)s, %(retrieval_ms)s, %(llm_ms)s, "
    "%(total_ms)s, %(code_version)s, %(data_version)s) RETURNING id"
)


def record(conn: psycopg.Connection, trace: Trace) -> int:
    """Store the trace and return its id. The caller's transaction is committed."""
    top, gap = _scores(trace.retrieved)
    row = {**trace.__dict__, "question_sha256": hashlib.sha256(trace.question.encode()).hexdigest(),
           "retrieved": Jsonb(trace.retrieved), "cited": Jsonb(trace.cited), "top_score": top, "score_gap": gap}
    trace_id = conn.execute(INSERT, row).fetchone()[0]
    conn.commit()
    return trace_id


def set_feedback(conn: psycopg.Connection, request_id: str, value: int, comment: str | None = None,
                 kind: str | None = None) -> bool:
    """Thumbs up (1) or down (-1) on a request, with an optional kind and comment; False if there is no such request.
    A new vote replaces the old one."""
    done = conn.execute("UPDATE query_traces SET feedback = %s, feedback_comment = %s, feedback_kind = %s WHERE request_id = %s",
                        (value, comment, kind, request_id)).rowcount == 1
    conn.commit()
    return done


def failures(conn: psycopg.Connection, since: timedelta, outcomes: tuple[str, ...] = FAILURES, limit: int = 50) -> list[dict]:
    """The latest requests the system could not answer, with what retrieval found, newest first."""
    with conn.cursor(row_factory=dict_row) as cur:
        return cur.execute(
            "SELECT id, created_at, lang, question, outcome, refusal_reason, error, retrieved, top_score, score_gap, feedback "
            "FROM query_traces WHERE created_at >= now() - %s AND outcome = ANY(%s) ORDER BY created_at DESC LIMIT %s",
            (since, list(outcomes), limit),
        ).fetchall()


def summary(conn: psycopg.Connection, since: timedelta) -> dict:
    """Requests by outcome, the share answered, tokens, cost and the median and 95th percentile of the total time."""
    with conn.cursor(row_factory=dict_row) as cur:
        by_outcome = {r["outcome"]: r["n"] for r in cur.execute(
            "SELECT outcome, count(*) AS n FROM query_traces WHERE created_at >= now() - %s GROUP BY outcome", (since,)
        ).fetchall()}
        totals = cur.execute(
            "SELECT count(*) AS n, coalesce(sum(tokens_in), 0) AS tokens_in, coalesce(sum(tokens_out), 0) AS tokens_out, "
            "coalesce(sum(cost_usd), 0)::float AS cost_usd, "
            "percentile_cont(0.5) WITHIN GROUP (ORDER BY total_ms) AS p50_ms, "
            "percentile_cont(0.95) WITHIN GROUP (ORDER BY total_ms) AS p95_ms "
            "FROM query_traces WHERE created_at >= now() - %s AND outcome = 'answered'", (since,)).fetchone()
    n = sum(by_outcome.values())
    return {"requests": n, "by_outcome": by_outcome, "answered_share": by_outcome.get("answered", 0) / n if n else None,
            "answered": totals}


def expired(conn: psycopg.Connection, now: datetime | None = None) -> int:
    return conn.execute("SELECT count(*) FROM query_traces WHERE expires_at <= %s", (now or datetime.now(UTC),)).fetchone()[0]


def purge(conn: psycopg.Connection, now: datetime | None = None) -> int:
    """Delete the traces past their expiry date; returns how many."""
    deleted = conn.execute("DELETE FROM query_traces WHERE expires_at <= %s", (now or datetime.now(UTC),)).rowcount
    conn.commit()
    return deleted


def export_candidates(conn: psycopg.Connection, since: timedelta, path: Path) -> int:
    """Write the failures as JSON lines for review. The questions may hold personal data and nothing is verified:
    a person reads each one, removes personal data and adds the gold before it can enter the eval set."""
    if path.exists():
        raise FileExistsError(f"{path} exists; choose another name")
    rows = failures(conn, since, limit=10_000)
    lines = [json.dumps({
        "trace_id": r["id"], "created_at": r["created_at"].isoformat(), "lang": r["lang"], "question": r["question"],
        "outcome": r["outcome"], "refusal_reason": r["refusal_reason"], "retrieved": [x["label"] for x in r["retrieved"]],
        "status": "unreviewed",
    }, ensure_ascii=False) for r in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""))
    return len(lines)
