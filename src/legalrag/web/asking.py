"""Answering one question for the service (step 0f): the cache, the engine, the traces. The route `/ask` and the cache
warm-up both call `answer_question`, so they give the same cache keys and the same traces.
"""

import logging
import time
from contextlib import nullcontext
from dataclasses import dataclass

from pydantic import ValidationError

from legalrag.answering import answer, cache, pii, rag, trace
from legalrag.answering.logs import log_event
from legalrag.web import schemas

log = logging.getLogger("legalrag.web")
UPSTREAM_FAILURES = ("llm_error", "parse_error")  # the model side failed: 502, the articles are still returned
NOT_STORED = ("request_id", "cached", "retry_after", "question_fr", "masked", "question_masked")  # the parts of a reply that belong to one request


@dataclass(frozen=True)
class Settings:
    # Name of the header our own proxy sets to the visitor's address (decision 3); none: the address of the connection.
    # Only safe when the service can be reached through that proxy alone, since any visitor could write the header.
    client_ip_header: str | None = None
    feedback_per_minute: int = 10  # per client
    search_per_minute: int = 30  # per client; /search costs no model call but uses the CPU (about 4 searches a second in all)
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


def limited_trace(engine: rag.AnswerEngine, settings: Settings, reply: schemas.AskReply, question: str, client: str | None,
                  key: str) -> trace.Trace:
    """The trace of a request refused by the cached-replies limit: it does not count toward any limit."""
    return trace.Trace(
        request_id=reply.request_id, lang="fr", question=question, mode="answer", outcome="rate_limited", client_hash=client,
        refusal_reason=reply.reason, retrieved=[{"label": a.label, "score": a.similarity} for a in reply.articles],
        model=engine.model, prompt_id=engine.prompt_id, code_version=settings.code_version, data_version=settings.data_version,
        cache_key=key)


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


class Refused(Exception):
    """A request that cannot be served: the HTTP status, a short reason, and the seconds to wait when it is a limit."""

    def __init__(self, status: int, detail: str, retry_after: int | None = None) -> None:
        super().__init__(detail)
        self.status, self.detail, self.retry_after = status, detail, retry_after


def stored_answer(connect, request_id: str) -> tuple[str, dict, str | None]:
    """(the cache key, the stored reply, its English translation or None) of the answer given for a request; `Refused` when
    there is no such answer (404), or it is no longer stored (410)."""
    with connect() as conn:
        row = conn.execute("SELECT cache_key, outcome FROM query_traces WHERE request_id = %s AND mode = 'answer'", (request_id,)).fetchone()
        if not row or row[1] not in ("answered", "cache_hit") or not row[0]:
            raise Refused(404, "no such answer")
        found = cache.reply_and_translation(conn, row[0])
    if found is None:
        raise Refused(410, "this answer is no longer stored")
    return row[0], found[0], found[1]


def english_of_answer(engine: rag.AnswerEngine, connect, settings: Settings, request_id: str,
                      client: str | None) -> schemas.TranslateAnswerReply:
    """The English translation of an answer that the service gave, found by the id of the request. It translates only a
    stored answer (never text sent by the visitor). A translation made before is returned at no cost. A new one is a model
    call: one request at a time for the visitor, the switch, the day's budget and the visitor's translation counters (per
    minute and per day) apply, the same answer is translated once even when several visitors ask at the same moment, and
    the result is stored with the answer."""
    key, stored_reply, english = stored_answer(connect, request_id)
    if english:
        return schemas.TranslateAnswerReply(request_id=request_id, english=english, stored=True)
    if not stored_reply.get("claims"):
        raise Refused(404, "nothing to translate")  # an answer with no sentence (an entry of another version of the reply)
    gate = engine.gate
    if gate is not None and not gate.begin(client):
        raise Refused(429, "another request is in progress for you", 2)
    try:
        with gate.single_flight("translate|" + key) if gate is not None else nullcontext():
            _, stored_reply, english = stored_answer(connect, request_id)  # another visitor may have made it while this one waited
            if english:
                return schemas.TranslateAnswerReply(request_id=request_id, english=english, stored=True)
            verdict = gate.check_translation(client) if gate is not None else None
            if verdict is not None and not verdict.allowed:
                raise Refused(verdict.status, verdict.reason, verdict.retry_after)
            try:
                lines, cost = engine.translate_answer(schemas.numbered_claims(stored_reply["claims"]))
            except Exception as error:  # any failure of the call or a result that moved a citation: nothing is shown
                log_event(log, "translate_answer_failed", request_id, logging.ERROR, error=type(error).__name__)
                raise Refused(502, "the translation could not be made") from error
            english = " ".join(lines)
            try:
                with connect() as conn:
                    cache.set_translation(conn, key, english)
            except Exception as error:  # noqa: BLE001 - storing is an optimisation: the visitor still gets the translation
                log_event(log, "cache_failed", request_id, logging.ERROR, error=type(error).__name__)
            write_trace(connect, translation_trace(engine, settings, "en", client, "answered", cost))
            return schemas.TranslateAnswerReply(request_id=request_id, english=english)
    finally:
        if gate is not None:
            gate.end(client)


def translation_trace(engine: rag.AnswerEngine, settings: Settings, lang: str, client: str | None, outcome: str,
                      cost: float | None) -> trace.Trace:
    """A translation is traced apart (mode "translate", no text), with its cost: the day's budget and the visitor's
    translation counters read these rows, whatever happens to the answer that follows a translated question."""
    return trace.Trace(request_id=trace.new_request_id(), lang=lang, question="", mode="translate", outcome=outcome, client_hash=client,
                       model=engine.model, cost_usd=cost, code_version=settings.code_version, data_version=settings.data_version)


def translate_question(engine: rag.AnswerEngine, connect, settings: Settings, question: str,
                       client: str | None) -> tuple[str | None, tuple[schemas.AskReply, int] | None]:
    """The visitor asked to translate the question into French first. The translation is a model call with its own trace
    and counters (per minute and per day, apart from the answers): it is refused when the visitor is over them, when the
    model is switched off or the day's budget is used up, and no model money is spent then. Returns (the French question,
    None), or (None, the failed reply and its status)."""
    verdict = engine.gate.check_translation(client) if engine.gate else None
    request_id = trace.new_request_id()
    if verdict is not None and not verdict.allowed:
        refused = schemas.AskReply(request_id=request_id, outcome=verdict.outcome, reason=verdict.reason, retry_after=verdict.retry_after)
        write_trace(connect, limited_trace(engine, settings, refused, question, client, None))
        return None, (refused, verdict.status)
    try:
        french, cost = engine.translate(question)
    except Exception as error:  # noqa: BLE001 - any failure of the call or a bad result is a failed translation
        log_event(log, "translate_failed", request_id, logging.ERROR, error=type(error).__name__)
        write_trace(connect, translation_trace(engine, settings, "fr", client, "llm_error", None))  # it counts: the call was made
        failed = schemas.AskReply(request_id=request_id, outcome="llm_error", reason="La traduction de la question a échoué.")
        return None, (failed, 502)
    write_trace(connect, translation_trace(engine, settings, "fr", client, "answered", cost))
    return pii.mask(french).text, None  # masked again: the model may write digits that the visitor spelled out


def answer_question(engine: rag.AnswerEngine, connect, settings: Settings, question: str, client: str | None,
                    warm: bool = False, translate: bool = False) -> tuple[schemas.AskReply, int]:
    """The reply and the HTTP status for one question, one request at a time for a visitor: a second request sent while
    the first is in progress is refused at once with a 429 (see `Limits.begin`), so that a burst cannot pass the counts."""
    gate = engine.gate
    if gate is None or warm:
        return answer_one(engine, connect, settings, question, client, warm, translate)
    if not gate.begin(client):
        busy = schemas.AskReply(request_id=trace.new_request_id(), outcome="rate_limited", retry_after=2, busy=True,
                                reason="une autre question est déjà en cours depuis votre connexion : attendez sa réponse")
        return busy, 429
    try:
        return answer_one(engine, connect, settings, question, client, warm, translate)
    finally:
        gate.end(client)


def answer_one(engine: rag.AnswerEngine, connect, settings: Settings, question: str, client: str | None,
               warm: bool = False, translate: bool = False) -> tuple[schemas.AskReply, int]:
    """A stored reply is served when there is one and the client is within the minute limit; otherwise the engine answers,
    and a stable reply is stored. `warm` (the warm-up) never reads the cache and leaves out the per-client limits.
    `translate`: the question is first translated into French (the visitor asked for it); the reply then carries the
    French question, and the answer is cached under it."""
    if translate:
        question, failed = translate_question(engine, connect, settings, question, client)
        if failed:
            return failed
        reply, status = answer_french_question(engine, connect, settings, question, client)
        reply.question_fr = question
        return reply, status
    return answer_french_question(engine, connect, settings, question, client, warm)


def answer_french_question(engine: rag.AnswerEngine, connect, settings: Settings, question: str, client: str | None,
                           warm: bool = False) -> tuple[schemas.AskReply, int]:
    """The same question asked by several visitors at once is answered once (`Limits.single_flight`): the others wait for
    the first, then read its answer from the memory."""
    key = cache_key(engine, settings, question)
    with engine.gate.single_flight(key) if engine.gate is not None and not warm else nullcontext():
        return answer_with_key(engine, connect, settings, question, client, warm, key)


def answer_with_key(engine: rag.AnswerEngine, connect, settings: Settings, question: str, client: str | None, warm: bool,
                    key: str) -> tuple[schemas.AskReply, int]:
    request_id = trace.new_request_id()
    started = time.monotonic()
    stored = None if warm else lookup(connect, key, request_id)
    reply = from_cache(stored, request_id) if stored is not None else None
    if reply is not None:
        verdict = engine.gate.check_cached(client) if engine.gate else None
        if verdict is None or verdict.allowed:
            elapsed = round((time.monotonic() - started) * 1000)
            write_trace(connect, hit_trace(engine, settings, reply, question, client, key, elapsed))
            log_event(log, "ask", request_id, outcome="cache_hit", total_ms=elapsed, cost_usd=0)
            return reply, 200
        # over the cached-replies limit: refuse with the stored articles; a fresh model call would only cost money
        refused = schemas.AskReply(request_id=request_id, outcome=verdict.outcome, reason=verdict.reason,
                                   articles=reply.articles, retry_after=verdict.retry_after)
        write_trace(connect, limited_trace(engine, settings, refused, question, client, key))
        log_event(log, "ask", request_id, outcome=verdict.outcome, total_ms=round((time.monotonic() - started) * 1000), cost_usd=0)
        return refused, verdict.status
    result = engine.respond(question, client, warm=warm).metadata["result"]
    write_trace(connect, result_trace(engine, settings, result, request_id, question, "answer", client, key))
    log_event(log, "ask", request_id, outcome=result.outcome, total_ms=result.total_ms, cost_usd=result.cost_usd)
    reply = schemas.reply_of(result, request_id)
    if result.outcome in cache.CACHEABLE:
        store(connect, key, result.outcome, reply, pinned=warm)  # only the warm-up asks the example questions
    return reply, 502 if result.outcome in UPSTREAM_FAILURES else result.status
