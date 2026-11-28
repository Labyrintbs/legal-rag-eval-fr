"""The HTTP service (step 0f, decisions 1 to 5 of docs/decisions/0008): `POST /ask`, `POST /search`, `POST /feedback`
and `GET /health` around the answer engine. Handlers are plain functions, so FastAPI runs each in a worker thread
and the blocking work (embedding, database, model call) does not stop other requests. Every request is traced:
the limits count the traces. The work of /ask (cache, engine, traces) is in `asking`, shared with the cache warm-up.
"""

import logging
import math
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

import psycopg
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from legalrag.answering import answer, cache, limits, pii, rag, search, trace
from legalrag.answering.logs import log_event
from legalrag.web import asking, schemas, warm
from legalrag.web.asking import Settings

log = logging.getLogger("legalrag.web")


def client_address(request: Request, header: str | None) -> str | None:
    """The address in the header named in the settings, or the address of the connection. A header with several values
    ("a, b, c") is read from the end: the last one is the value that our own proxy appended, while the first can be
    written by the visitor."""
    if header and (value := request.headers.get(header)):
        return value.split(",")[-1].strip() or None
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
            if len(self.events) > FORGET_AFTER:  # many addresses seen: forget the ones with nothing in the window
                self.events = defaultdict(deque, {k: v for k, v in self.events.items() if v and v[-1] > now - self.seconds})
            events = self.events[key]
            while events and events[0] <= now - self.seconds:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True

    def retry_after(self, key: str, now: float | None = None) -> int:
        """Seconds until the oldest event of this client leaves the window and one more is allowed."""
        now = time.monotonic() if now is None else now
        with self.lock:
            events = self.events[key]
            return max(1, math.ceil(events[0] + self.seconds - now)) if events else 1


STATIC = Path(__file__).with_name("static")
MAX_BODY = 16 * 1024  # bytes: 500 characters of any alphabet are at most 2 kB
FORGET_AFTER = 5000  # addresses kept by a `Recent` window before the idle ones are dropped
# The pages load only their own files; nothing is written into them from outside (the script builds the DOM with textContent).
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
    "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
}


def cache_control(request: Request) -> str:
    """How long a browser or a proxy may keep a reply: nothing from the API, a few minutes for the examples, and the pages
    and files only after asking again (their ETag makes that cheap), so that a deploy shows at once."""
    if request.method != "GET":
        return "no-store"
    if request.url.path == "/health":
        return "no-store"
    if request.url.path == "/examples":
        return "public, max-age=300"
    return "no-cache"


def create_app(engine: rag.AnswerEngine, connect, settings: Settings | None = None,
               warm_questions: list[str] | None = None, examples: list[dict] | None = None, docs: bool = False) -> FastAPI:
    """`warm_questions`: example questions to ask in the background at startup (decision 4); none: no warm-up.
    `examples`: what `GET /examples` sends to the page (see `examples.load`). `docs`: the interactive API docs (development)."""
    settings = settings or Settings()
    warm_status = warm.Status(state="running" if warm_questions else "off")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if warm_questions:
            threading.Thread(target=warm.run, args=(engine, connect, settings, warm_questions, warm_status), daemon=True).start()
        yield

    # The interactive docs load their script from a third-party CDN and describe every route: development only (`docs=True`).
    app = FastAPI(title="legal-rag-eval-fr", docs_url="/api/docs" if docs else None, redoc_url=None,
                  openapi_url="/api/openapi.json" if docs else None, lifespan=lifespan)
    feedback_window = Recent(settings.feedback_per_minute)
    search_window = Recent(settings.search_per_minute)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError) -> JSONResponse:
        """A 422 says which field is wrong and why, but never repeats the value: the visitor's text is not echoed back
        (and a value that cannot be written as UTF-8 would have broken the reply itself)."""
        problems = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in error.errors()]
        return JSONResponse({"detail": problems}, status_code=422)

    @app.exception_handler(limits.Overloaded)
    async def overloaded(request: Request, error: limits.Overloaded) -> JSONResponse:
        """Searches wait for the processor, two at a time; beyond a short queue the request is refused at once."""
        return JSONResponse({"detail": "the service is busy, try again in a moment"}, status_code=503, headers={"Retry-After": "3"})

    @app.exception_handler(psycopg.Error)
    async def database_failed(request: Request, error: psycopg.Error) -> JSONResponse:
        """The limits live in the database: when it cannot be reached the service cannot count, so it does not call the model
        (fail closed). The visitor gets a plain 503, never the text of the error."""
        log_event(log, "database_failed", None, logging.ERROR, error=type(error).__name__)
        return JSONResponse({"detail": "the service is temporarily unavailable"}, status_code=503, headers={"Retry-After": "30"})

    @app.middleware("http")
    async def limit_body(request: Request, call_next):
        """A request body is at most a few kilobytes (a question is 500 characters): refuse a larger or an unmeasured one before it is read."""
        if request.method in ("POST", "PUT", "PATCH"):
            length = request.headers.get("content-length")
            if "transfer-encoding" in request.headers:  # chunked framing makes the server ignore the declared length
                return JSONResponse({"detail": "chunked bodies are not accepted"}, status_code=411)
            if length is None:
                return JSONResponse({"detail": "content-length required"}, status_code=411)
            if not length.isdigit() or int(length) > MAX_BODY:
                return JSONResponse({"detail": "request too large"}, status_code=413)
        return await call_next(request)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # added last, so it wraps the others: every reply has the headers
        response = await call_next(request)
        if not (docs and request.url.path.startswith("/api/")):  # the docs page (development only) loads its script from a CDN
            response.headers.update(SECURITY_HEADERS)
            response.headers.setdefault("Cache-Control", cache_control(request))
        return response

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def home() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/method", include_in_schema=False)
    def method() -> FileResponse:
        return FileResponse(STATIC / "method.html")

    @app.get("/data", include_in_schema=False)
    def data() -> FileResponse:
        return FileResponse(STATIC / "data.html")

    @app.get("/privacy", include_in_schema=False)
    def privacy() -> FileResponse:
        return FileResponse(STATIC / "privacy.html")

    @app.get("/history", include_in_schema=False)
    def history() -> FileResponse:
        return FileResponse(STATIC / "history.html")

    @app.get("/examples", include_in_schema=False)
    def example_questions() -> list[dict]:
        return examples or []

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
        return schemas.HealthReply(status="ok", llm_enabled=enabled, cache_warm=warm_status.state, llm_host=settings.llm_host,
                                   llm_failing=engine.pulse.failing, llm_other_model=engine.pulse.other_model)

    @app.post("/search", response_model=schemas.SearchReply)
    def search_route(body: schemas.AskRequest, request: Request) -> schemas.SearchReply:
        request_id = trace.new_request_id()
        client = trace.client_hash(client_address(request, settings.client_ip_header))
        if not search_window.allow(client or "-"):  # no model money, but every search embeds the question on the CPU
            raise HTTPException(429, "too many searches, try again in a moment",
                                headers={"Retry-After": str(search_window.retry_after(client or "-"))})
        masked = pii.mask(body.question)  # from here on, only the masked question exists
        started = time.monotonic()
        nodes = engine.retriever.retrieve(masked.text)
        hits = rag.hits_of(nodes)
        weak = search.is_weak(hits, engine.threshold) and not rag.names_article(nodes)
        elapsed = round((time.monotonic() - started) * 1000)
        result = answer.Result("refused_weak_retrieval" if weak else "answered", "", hits, retrieval_ms=elapsed, total_ms=elapsed)
        asking.write_trace(connect, asking.result_trace(engine, settings, result, request_id, masked.text, "search", client, None))
        log_event(log, "search", request_id, outcome=result.outcome, total_ms=elapsed)
        return schemas.SearchReply(request_id=request_id, articles=schemas.articles_of(hits), weak=weak, masked=masked.kinds)

    @app.post("/ask", response_model=schemas.AskReply, responses={429: {"model": schemas.AskReply}, 502: {"model": schemas.AskReply},
                                                                  503: {"model": schemas.AskReply}})
    def ask(body: schemas.AskRequest, request: Request, response: Response) -> schemas.AskReply:
        client = trace.client_hash(client_address(request, settings.client_ip_header))
        masked = pii.mask(body.question)  # before the cache, the traces, the translation and the model
        reply, status = asking.answer_question(engine, connect, settings, masked.text, client, translate=body.translate)
        if masked.kinds:
            reply.masked, reply.question_masked = masked.kinds, masked.text
        response.status_code = status
        if reply.retry_after:
            response.headers["Retry-After"] = str(reply.retry_after)
        return reply

    @app.post("/translate-answer", response_model=schemas.TranslateAnswerReply)
    def translate_answer(body: schemas.TranslateAnswerRequest, request: Request) -> schemas.TranslateAnswerReply:
        client = trace.client_hash(client_address(request, settings.client_ip_header))
        try:
            return asking.english_of_answer(engine, connect, settings, body.request_id, client)
        except asking.Refused as refused:
            headers = {"Retry-After": str(refused.retry_after)} if refused.retry_after else None
            raise HTTPException(refused.status, refused.detail, headers=headers) from refused

    @app.post("/feedback")
    def feedback(body: schemas.FeedbackRequest, request: Request) -> dict:
        client = trace.client_hash(client_address(request, settings.client_ip_header))
        if not feedback_window.allow(client or "-"):
            raise HTTPException(429, "too many feedback messages, try again in a moment",
                                headers={"Retry-After": str(feedback_window.retry_after(client or "-"))})
        comment = pii.mask(body.comment).text if body.comment else None  # a comment is free text: masked like a question
        with connect() as conn:
            if not trace.set_feedback(conn, body.request_id, body.value, comment, body.kind):
                raise HTTPException(404, "no such request")
            if body.value == -1:
                cache.drop_for_vote(conn, body.request_id, client)
        log_event(log, "feedback", body.request_id, value=body.value, kind=body.kind)
        return {"ok": True}

    return app
