"""The real wiring of the service (step 0f): bge-m3 loaded once in this process, DeepSeek, the limits, the database.
`production_app` is the factory that uvicorn calls (`legalrag serve`). It fails at start, not on the first request,
when a setting is missing. Tests build the app with `app.create_app` and fakes instead.
"""

import os
import threading

from fastapi import FastAPI
from llama_index.llms.deepseek import DeepSeek

from legalrag.answering import limits, rag
from legalrag.answering.logs import setup as setup_logs
from legalrag.evaluation.questiongen import load_prompts
from legalrag.index import db, embed
from legalrag.web.app import Settings, create_app

EMBED_AT_ONCE = 2  # decision 1: questions embedded at the same time; the others wait
MODEL = "deepseek-flash"  # decision of 0d: thinking off
PROMPT_ID = "answer.v3"
RUN = "default"


class LimitedEmbedder:
    """Lets at most `at_once` calls into the model together; the CPU is shared with the web server."""

    def __init__(self, embedder, at_once: int = EMBED_AT_ONCE) -> None:
        self.embedder, self.slots = embedder, threading.BoundedSemaphore(at_once)

    def encode_queries(self, texts: list[str], batch_size: int):
        with self.slots:
            return self.embedder.encode_queries(texts, batch_size)


def production_app() -> FastAPI:
    setup_logs()
    for name in ("DEEPSEEK_API_KEY", "TRACE_SECRET"):
        if not os.environ.get(name):
            raise RuntimeError(f"{name} is not set")
    api_key = os.environ["DEEPSEEK_API_KEY"]
    prompt = load_prompts(db.ROOT / "prompts" / "answer.yaml")["prompts"][PROMPT_ID]
    llm = DeepSeek(model=MODEL, api_key=api_key, temperature=0, max_tokens=prompt["max_tokens"],
                   additional_kwargs={"extra_body": {"thinking": {"type": "disabled"}}})
    embedder = LimitedEmbedder(embed.SentenceTransformerEmbedder(os.environ.get("EMBED_DEVICE", "cpu")))
    with db.connect() as conn:
        run_id = conn.execute("SELECT id FROM chunking_runs WHERE name = %s", (RUN,)).fetchone()[0]
    engine = rag.AnswerEngine(
        retriever=rag.LegalRetriever(db.connect, run_id, embedder, "fr"), postprocessor=rag.NumberUnits(), llm=llm,
        prompt=prompt, model=MODEL, prompt_id=PROMPT_ID, gate=limits.Limits(db.connect))
    settings = Settings(client_ip_header=os.environ.get("CLIENT_IP_HEADER") or None,
                        code_version=os.environ.get("CODE_VERSION"), data_version=os.environ.get("DATA_VERSION"))
    return create_app(engine, db.connect, settings)
