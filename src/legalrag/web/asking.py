"""Answering one question for the service (step 0f): the cache, the engine, the traces. The route `/ask` and the cache
warm-up both call `answer_question`, so they give the same cache keys and the same traces.
"""

import logging
import time
from dataclasses import dataclass

from pydantic import ValidationError

from legalrag.answering import answer, cache, rag, trace
from legalrag.answering.logs import log_event
from legalrag.web import schemas

log = logging.getLogger("legalrag.web")
UPSTREAM_FAILURES = ("llm_error", "parse_error")  # the model side failed: 502, the articles are still returned
NOT_STORED = ("request_id", "cached", "retry_after")  # the parts of a reply that belong to one request


@dataclass(frozen=True)
class Settings:
    # Name of the header our own proxy sets to the visitor's address (decision 3); none: the address of the connection.
    # Only safe when the service can be reached through that proxy alone, since any visitor could write the header.
    client_ip_header: str | None = None
    feedback_per_minute: int = 10  # per client
    code_version: str | None = None  # a deploy with another code version starts with an empty cache (decision 4)
    data_version: str | None = None


def cache_key(engine: rag.AnswerEngine, settings: Settings, question: str) -> str:
    return cache.key_of(question, model=engine.model, prompt_id=engine.prompt_id, threshold=engine.threshold,
                        data_version=settings.data_version or "", code_version=settings.code_version or "")


def write_trace(connect, row: trace.Trace) -> None:
    """A failed write is logged, not shown: the visitor still gets the reply."""
    try:
        with connect() as conn:
            trace.record(conn, row)
    except Exception as error:  # noqa: BLE001 - tracing must never break a request
        log_event(log, "trace_failed", row.request_id, logging.ERROR, error=type(error).__name__)


def result_trace(engine: rag.AnswerEngine, settings: Settings, result: answer.Result, request_id: str, question: str,
                 mode: str, client: str | None, key: str | None) -> trace.Trace:
    row = answer.to_trace(result, request_id, "fr", question, mode, engine.model, engine.prompt_id, client,
                          settings.code_version, settings.data_version)
    if mode == "search":
        row.answer = None
    row.cache_key = key
    return row


def hit_trace(engine: rag.AnswerEngine, settings: Settings, reply: schemas.AskReply, question: str, client: str | None,
              key: str, total_ms: int) -> trace.Trace:
    """The trace of a reply served from the cache: no model call, no cost."""
    return trace.Trace(
        request_id=reply.request_id, lang="fr", question=question, mode="answer", outcome="cache_hit", client_hash=client,
        retrieved=[{"label": a.label, "score": a.similarity} for a in reply.articles],
        cited=[{"label": c.label, "unit": n} for claim in reply.claims for c in claim.citations for n in c.units],
        model=engine.model, prompt_id=engine.prompt_id, cost_usd=0, total_ms=total_ms,
        code_version=settings.code_version, data_version=settings.data_version, cache_key=key)


def lookup(connect, key: str, request_id: str) -> dict | None:
    """A failure of the cache is logged and counts as a miss."""
    try:
        with connect() as conn:
            return cache.get(conn, key)
    except Exception as error:  # noqa: BLE001 - the cache must never break a request
        log_event(log, "cache_failed", request_id, logging.ERROR, error=type(error).__name__)
        return None


def from_cache(stored: dict, request_id: str) -> schemas.AskReply | None:
    """The stored reply as a reply to this request; none when it does not fit the current template (an entry made by
    another version of the reply shape), which counts as a miss."""
    try:
        return schemas.AskReply.model_validate({**stored, "request_id": request_id, "cached": True})
    except ValidationError:
        return None


def store(connect, key: str, outcome: str, reply: schemas.AskReply, pinned: bool = False) -> None:
    try:
        with connect() as conn:
            cache.put(conn, key, outcome, reply.model_dump(mode="json", exclude=set(NOT_STORED)), pinned=pinned)
    except Exception as error:  # noqa: BLE001 - the cache must never break a request
        log_event(log, "cache_failed", reply.request_id, logging.ERROR, error=type(error).__name__)


def answer_question(engine: rag.AnswerEngine, connect, settings: Settings, question: str, client: str | None,
                    warm: bool = False) -> tuple[schemas.AskReply, int]:
    """The reply and the HTTP status for one question. A stored reply is served when there is one and the client is
    within the minute limit; otherwise the engine answers, and a stable reply is stored. `warm` (the warm-up) never
    reads the cache and leaves out the per-client limits."""
    request_id = trace.new_request_id()
    started = time.monotonic()
    key = cache_key(engine, settings, question)
    stored = None if warm else lookup(connect, key, request_id)
    reply = from_cache(stored, request_id) if stored is not None else None
    if reply is not None and (engine.gate is None or engine.gate.check_cached(client).allowed):
        elapsed = round((time.monotonic() - started) * 1000)
        write_trace(connect, hit_trace(engine, settings, reply, question, client, key, elapsed))
        log_event(log, "ask", request_id, outcome="cache_hit", total_ms=elapsed, cost_usd=0)
        return reply, 200
    result = engine.respond(question, client, warm=warm).metadata["result"]
    write_trace(connect, result_trace(engine, settings, result, request_id, question, "answer", client, key))
    log_event(log, "ask", request_id, outcome=result.outcome, total_ms=result.total_ms, cost_usd=result.cost_usd)
    reply = schemas.reply_of(result, request_id)
    if result.outcome in cache.CACHEABLE:
        store(connect, key, result.outcome, reply, pinned=warm)  # only the warm-up asks the example questions
    return reply, 502 if result.outcome in UPSTREAM_FAILURES else result.status
