"""The HTTP service (step 0f, decisions 1 to 5 of docs/decisions/0008): `POST /ask`, `POST /search`, `POST /feedback`
and `GET /health` around the answer engine. Handlers are plain functions, so FastAPI runs each in a worker thread
and the blocking work (embedding, database, model call) does not stop other requests. Every request is traced:
the limits count the traces.
"""

import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from legalrag.answering import answer, limits, rag, search, trace
from legalrag.answering.logs import log_event
from legalrag.web import schemas

log = logging.getLogger("legalrag.web")
UPSTREAM_FAILURES = ("llm_error", "parse_error")  # the model side failed: 502, the articles are still returned


@dataclass(frozen=True)
class Settings:
    # Name of the header our own proxy sets to the visitor's address (decision 3); none: the address of the connection.
    # Only safe when the service can be reached through that proxy alone, since any visitor could write the header.
    client_ip_header: str | None = None
    feedback_per_minute: int = 10  # per client
    code_version: str | None = None
    data_version: str | None = None


def client_address(request: Request, header: str | None) -> str | None:
    if header and (value := request.headers.get(header)):
        return value.split(",")[0].strip() or None
    return request.client.host if request.client else None


class Recent:
    """At most `limit` events per client in the last `seconds`, in this process (the service runs one process)."""

    def __init__(self, limit: int, seconds: float = 60) -> None:
        self.limit, self.seconds = limit, seconds
        self.events: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self.lock:
            events = self.events[key]
            while events and events[0] <= now - self.seconds:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True


def create_app(engine: rag.AnswerEngine, connect, settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="legal-rag-eval-fr", docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")
    feedback_window = Recent(settings.feedback_per_minute)

    def write_trace(result: answer.Result, request_id: str, question: str, mode: str, client: str | None) -> None:
        """A failed write is logged, not shown: the visitor still gets the answer."""
        try:
            row = answer.to_trace(result, request_id, "fr", question, mode, engine.model, engine.prompt_id, client,
                                  settings.code_version, settings.data_version)
            if mode == "search":
                row.answer = None
            with connect() as conn:
                trace.record(conn, row)
        except Exception as error:  # noqa: BLE001 - tracing must never break a request
            log_event(log, "trace_failed", request_id, logging.ERROR, error=type(error).__name__)

    @app.get("/health")
    def health() -> JSONResponse:
        try:
            with connect() as conn:
                enabled = limits.llm_enabled(conn)
        except psycopg.Error:
            return JSONResponse({"status": "database_unavailable"}, status_code=503)
        return JSONResponse({"status": "ok", "llm_enabled": enabled})

    @app.post("/search", response_model=schemas.SearchReply)
    def search_route(body: schemas.AskRequest, request: Request) -> schemas.SearchReply:
        request_id = trace.new_request_id()
        client = trace.client_hash(client_address(request, settings.client_ip_header))
        started = time.monotonic()
        hits = rag.hits_of(engine.retriever.retrieve(body.question))
        weak = search.is_weak(hits, engine.threshold)
        elapsed = round((time.monotonic() - started) * 1000)
        result = answer.Result("refused_weak_retrieval" if weak else "answered", "", hits, retrieval_ms=elapsed, total_ms=elapsed)
        write_trace(result, request_id, body.question, "search", client)
        log_event(log, "search", request_id, outcome=result.outcome, total_ms=elapsed)
        return schemas.SearchReply(request_id=request_id, articles=schemas.articles_of(hits), weak=weak)

    @app.post("/ask", response_model=schemas.AskReply, responses={429: {"model": schemas.AskReply}, 502: {"model": schemas.AskReply},
                                                                  503: {"model": schemas.AskReply}})
    def ask(body: schemas.AskRequest, request: Request) -> JSONResponse:
        request_id = trace.new_request_id()
        client = trace.client_hash(client_address(request, settings.client_ip_header))
        result = engine.respond(body.question, client).metadata["result"]
        write_trace(result, request_id, body.question, "answer", client)
        log_event(log, "ask", request_id, outcome=result.outcome, total_ms=result.total_ms, cost_usd=result.cost_usd)
        status = 502 if result.outcome in UPSTREAM_FAILURES else result.status
        headers = {"Retry-After": str(result.retry_after)} if result.retry_after else {}
        return JSONResponse(schemas.reply_of(result, request_id).model_dump(), status_code=status, headers=headers)

    @app.post("/feedback")
    def feedback(body: schemas.FeedbackRequest, request: Request) -> dict:
        client = trace.client_hash(client_address(request, settings.client_ip_header)) or "-"
        if not feedback_window.allow(client):
            raise HTTPException(429, "too many feedback messages, try again in a minute", headers={"Retry-After": "60"})
        with connect() as conn:
            if not trace.set_feedback(conn, body.request_id, body.value, body.comment, body.kind):
                raise HTTPException(404, "no such request")
        log_event(log, "feedback", body.request_id, value=body.value, kind=body.kind)
        return {"ok": True}

    return app
