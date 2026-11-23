"""The HTTP service (step 0f, decisions 1 to 5 of docs/decisions/0008): `POST /ask`, `POST /search`, `POST /feedback`
and `GET /health` around the answer engine. Handlers are plain functions, so FastAPI runs each in a worker thread
and the blocking work (embedding, database, model call) does not stop other requests. Every request is traced:
the limits count the traces. The work of /ask (cache, engine, traces) is in `asking`, shared with the cache warm-up.
"""

import logging
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, HTTPException, Request, Response

from legalrag.answering import answer, cache, limits, rag, search, trace
from legalrag.answering.logs import log_event
from legalrag.web import asking, schemas, warm
from legalrag.web.asking import Settings

log = logging.getLogger("legalrag.web")


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


def create_app(engine: rag.AnswerEngine, connect, settings: Settings | None = None,
               warm_questions: list[str] | None = None) -> FastAPI:
    """`warm_questions`: example questions to ask in the background at startup (decision 4); none: no warm-up."""
    settings = settings or Settings()
    warm_status = warm.Status(state="running" if warm_questions else "off")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if warm_questions:
            threading.Thread(target=warm.run, args=(engine, connect, settings, warm_questions, warm_status), daemon=True).start()
        yield

    app = FastAPI(title="legal-rag-eval-fr", docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json",
                  lifespan=lifespan)
    feedback_window = Recent(settings.feedback_per_minute)

    # The routes below set a status or a header on `response` (a draft FastAPI hands in) and return the data: FastAPI
    # then checks it against `response_model` before sending. See docs/decisions/0008 (build notes).
    @app.get("/health", response_model=schemas.HealthReply, responses={503: {"model": schemas.HealthReply}})
    def health(response: Response) -> schemas.HealthReply:
        try:
            with connect() as conn:
                enabled = limits.llm_enabled(conn)
        except psycopg.Error:
            response.status_code = 503
            return schemas.HealthReply(status="database_unavailable")
        return schemas.HealthReply(status="ok", llm_enabled=enabled, cache_warm=warm_status.state)

    @app.post("/search", response_model=schemas.SearchReply)
    def search_route(body: schemas.AskRequest, request: Request) -> schemas.SearchReply:
        request_id = trace.new_request_id()
        client = trace.client_hash(client_address(request, settings.client_ip_header))
        started = time.monotonic()
        hits = rag.hits_of(engine.retriever.retrieve(body.question))
        weak = search.is_weak(hits, engine.threshold)
        elapsed = round((time.monotonic() - started) * 1000)
        result = answer.Result("refused_weak_retrieval" if weak else "answered", "", hits, retrieval_ms=elapsed, total_ms=elapsed)
        asking.write_trace(connect, asking.result_trace(engine, settings, result, request_id, body.question, "search", client, None))
        log_event(log, "search", request_id, outcome=result.outcome, total_ms=elapsed)
        return schemas.SearchReply(request_id=request_id, articles=schemas.articles_of(hits), weak=weak)

    @app.post("/ask", response_model=schemas.AskReply, responses={429: {"model": schemas.AskReply}, 502: {"model": schemas.AskReply},
                                                                  503: {"model": schemas.AskReply}})
    def ask(body: schemas.AskRequest, request: Request, response: Response) -> schemas.AskReply:
        client = trace.client_hash(client_address(request, settings.client_ip_header))
        reply, status = asking.answer_question(engine, connect, settings, body.question, client)
        response.status_code = status
        if reply.retry_after:
            response.headers["Retry-After"] = str(reply.retry_after)
        return reply

    @app.post("/feedback")
    def feedback(body: schemas.FeedbackRequest, request: Request) -> dict:
        client = trace.client_hash(client_address(request, settings.client_ip_header))
        if not feedback_window.allow(client or "-"):
            raise HTTPException(429, "too many feedback messages, try again in a minute", headers={"Retry-After": "60"})
        with connect() as conn:
            if not trace.set_feedback(conn, body.request_id, body.value, body.comment, body.kind):
                raise HTTPException(404, "no such request")
            if body.value == -1:
                cache.drop_for_vote(conn, body.request_id, client)
        log_event(log, "feedback", body.request_id, value=body.value, kind=body.kind)
        return {"ok": True}

    return app
