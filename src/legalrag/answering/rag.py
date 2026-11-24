"""The LlamaIndex layer of the answer path (decision 4 of docs/decisions/0006): our exact search as a retriever,
the numbering of the legal units as a node post-processor, and a query engine that asks the model through the
LlamaIndex DeepSeek connector. The checks stay in plain code (`answer`, `search`, `units`). The engine calls
`llm.chat` with JSON mode, not `structured_predict`, because only `chat` returns the token usage that the
trace needs.
"""

import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import psycopg
from llama_index.core.base.response.schema import Response
from llama_index.core.llms import ChatMessage
from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.query_engine import CustomQueryEngine
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode
from pydantic import ValidationError

from legalrag import llm as costs
from legalrag.answering import answer, articlenum, limits, search
from legalrag.answering.units import Unit, split_units
from legalrag.index.embed import MODEL, embed_queries

MAX_TRANSLATED = 500  # the longest question the service accepts
MARKS = re.compile(r"\[\d+\]")  # the citation numbers of an answer


class LegalRetriever(BaseRetriever):
    """Our exact dense search: one node per article (its best chunk), the score is the cosine similarity.
    With `article_rule` the articles that the question names by number come first (decision of 0f part 3); their
    nodes carry `named` in the metadata."""

    def __init__(self, connect: Callable[[], psycopg.Connection], run_id: int, embedder, lang: str,
                 k: int = search.TOP_ARTICLES, model: str = MODEL, article_rule: bool = False) -> None:
        super().__init__()
        self.connect, self.run_id, self.embedder, self.lang, self.k, self.model = connect, run_id, embedder, lang, k, model
        self.article_rule = article_rule

    def _retrieve(self, query_bundle: QueryBundle) -> list[NodeWithScore]:
        question = query_bundle.query_str
        vector = embed_queries([question], self.embedder)[0]
        with self.connect() as conn:
            hits = search.top_chunks(conn, self.run_id, self.lang, vector, self.k, self.model)
            named = search.named_chunks(conn, self.run_id, self.lang, vector, articlenum.named_keys(question), self.model) \
                if self.article_rule else []
        labels = {h.label for h in named}
        ranking = (named + [h for h in hits if h.label not in labels])[: self.k]
        return [NodeWithScore(node=TextNode(id_=f"{h.label}#{h.chunk_index}", text=h.text, metadata={
            "label": h.label, "chunk_index": h.chunk_index, "header": h.header, "section_path": h.section_path,
            "url": h.url, "named": h.label in labels}), score=h.similarity) for h in ranking]


def names_article(nodes: list[NodeWithScore]) -> bool:
    """True when the question named an article that exists: the weak-retrieval check does not apply then."""
    return any(n.node.metadata.get("named") for n in nodes)


class NumberUnits(BaseNodePostprocessor):
    """Adds the legal units of each node (start, end, lead-in) to its metadata; the text is not changed."""

    def _postprocess_nodes(self, nodes: list[NodeWithScore], query_bundle: QueryBundle | None = None) -> list[NodeWithScore]:
        for n in nodes:
            n.node.metadata["units"] = [[u.start, u.end, u.lead] for u in split_units(n.node.text)]
        return nodes


def hits_of(nodes: list[NodeWithScore]) -> list[search.Hit]:
    return [search.Hit(n.node.metadata["label"], n.node.metadata["chunk_index"], n.node.metadata["header"], n.node.text,
                       float(n.score), n.node.metadata["section_path"], n.node.metadata["url"]) for n in nodes]


def sources_of(nodes: list[NodeWithScore]) -> list[answer.Source]:
    return [answer.Source(i, hit, [Unit(*u) for u in n.node.metadata["units"]])
            for i, (hit, n) in enumerate(zip(hits_of(nodes), nodes, strict=True), 1)]


class AnswerEngine(CustomQueryEngine):
    """Question in, `answer.Result` out (in the metadata of the response)."""

    retriever: BaseRetriever
    postprocessor: BaseNodePostprocessor
    llm: Any
    prompt: dict
    model: str
    prompt_id: str
    threshold: float = search.WEAK_THRESHOLD
    ledger_label: str | None = None  # development runs also append their calls to the development ledger
    gate: Any = None  # a limits.Limits (rate limits and kill switch); none in development runs
    translate_prompt: dict | None = None  # the prompt that turns a visitor's question into French (`translate`)
    translate_answer_prompt: dict | None = None  # the prompt that turns the sentences of an answer into English

    def custom_query(self, query_str: str) -> Response:
        return self.respond(query_str)

    def translate_answer(self, lines: list[str]) -> tuple[list[str], float | None]:
        """The sentences of an answer in English, and the cost. Raises when the lines or the citation numbers of the result
        are not the ones that went in: a translation that moved or lost a citation is never shown."""
        if not self.translate_answer_prompt:
            raise RuntimeError("no answer translation prompt")
        prompt = self.translate_answer_prompt
        messages = [ChatMessage(role="system", content=prompt["system"].strip()),
                    ChatMessage(role="user", content=prompt["user"].format(text="\n".join(lines)))]
        reply = self.llm.chat(messages)
        english = [line.strip() for line in (reply.message.content or "").splitlines() if line.strip()]
        if len(english) != len(lines) or any(MARKS.findall(a) != MARKS.findall(b) for a, b in zip(lines, english, strict=True)):
            raise ValueError("the translation does not keep the lines and the citation numbers")
        tokens = answer.usage_of(getattr(reply.raw, "usage", None))
        cost = self.cost(tokens)
        self.append_ledger(tokens, cost)
        return english, cost

    def translate(self, question: str) -> tuple[str, float | None]:
        """The question in French and the cost of the call. Raises when the call fails or the result is not a question
        of the allowed length: the caller turns that into a failed request."""
        if not self.translate_prompt:
            raise RuntimeError("no translation prompt")
        messages = [ChatMessage(role="system", content=self.translate_prompt["system"].strip()),
                    ChatMessage(role="user", content=self.translate_prompt["user"].format(question=question))]
        reply = self.llm.chat(messages)
        french = " ".join((reply.message.content or "").split()).strip("\"'« »")
        if not french or len(french) > MAX_TRANSLATED:
            raise ValueError("the translation is empty or too long")
        tokens = answer.usage_of(getattr(reply.raw, "usage", None))
        cost = self.cost(tokens)
        self.append_ledger(tokens, cost)
        return french, cost

    def respond(self, question: str, client: str | None = None, warm: bool = False) -> Response:
        """Search, then the weak check, then the limits, then the model; the articles come back in every case.
        `warm` (the cache warm-up has no client) leaves out the per-client limits and keeps the switch and the budget."""
        started = time.monotonic()
        nodes = self.retriever.retrieve(question)
        hits = hits_of(nodes)
        retrieval_ms = round((time.monotonic() - started) * 1000)
        if search.is_weak(hits, self.threshold) and not names_article(nodes):
            top = f"{hits[0].similarity:.2f}" if hits else "none"
            result = answer.Result("refused_weak_retrieval", f"(no answer: nothing close enough found, best {top})", hits,
                                   reason=f"top similarity {top} below {self.threshold:.2f}", retrieval_ms=retrieval_ms)
        else:
            verdict = (self.gate.check(client, per_client=False) if warm else self.gate.check(client)) if self.gate else limits.ALLOWED
            if verdict.allowed:
                result = self.ask(question, self.postprocessor.postprocess_nodes(nodes), hits, retrieval_ms)
            else:
                result = answer.Result(verdict.outcome, f"(no answer: {verdict.reason})", hits, reason=verdict.reason,
                                       retrieval_ms=retrieval_ms, status=verdict.status, retry_after=verdict.retry_after)
        result.total_ms = round((time.monotonic() - started) * 1000)
        return Response(response=result.text, source_nodes=nodes, metadata={"result": result})

    def ask(self, question: str, nodes: list[NodeWithScore], hits: list[search.Hit], retrieval_ms: int) -> answer.Result:
        sources = sources_of(nodes)
        messages = [ChatMessage(role="system", content=self.prompt["system"].strip()),
                    ChatMessage(role="user", content=self.prompt["user"].format(context=answer.context(sources), question=question))]
        started = time.monotonic()
        try:
            reply = self.llm.chat(messages, response_format={"type": "json_object"})
        except Exception as error:  # noqa: BLE001 - any failure of the call (network, timeout, API) is an llm_error
            return answer.Result("llm_error", "(no answer: the model could not be reached)", hits, error=type(error).__name__,
                                 retrieval_ms=retrieval_ms, llm_ms=round((time.monotonic() - started) * 1000))
        llm_ms = round((time.monotonic() - started) * 1000)
        tokens = answer.usage_of(getattr(reply.raw, "usage", None))
        cost = self.cost(tokens)
        self.append_ledger(tokens, cost)
        common = {"hits": hits, "raw": reply.message.content, "tokens_in": tokens[0], "tokens_out": tokens[1],
                  "tokens_cached": tokens[2], "cost_usd": cost, "retrieval_ms": retrieval_ms, "llm_ms": llm_ms}
        try:
            model_answer = answer.ModelAnswer.model_validate_json(reply.message.content or "")
        except (ValidationError, ValueError):
            return answer.Result("parse_error", "(no answer: the reply could not be read)", **common)
        resolved = answer.resolve(model_answer, sources)
        text = answer.render(resolved)
        return answer.Result(resolved.outcome, text, resolved=resolved, reason=resolved.reason, **common)

    def cost(self, tokens: tuple[int | None, int | None, int | None]) -> float | None:
        if self.model not in costs.PEAK_PRICES or tokens[0] is None:
            return None
        cached = tokens[2] or 0
        return costs.cost_usd(self.model, cached, tokens[0] - cached, tokens[1] or 0, datetime.now(UTC))

    def append_ledger(self, tokens: tuple[int | None, int | None, int | None], cost: float | None) -> None:
        if self.ledger_label and cost is not None:
            costs.append_ledger(costs.LEDGER, {
                "type": "call", "time": datetime.now(UTC).isoformat(timespec="seconds"), "label": self.ledger_label,
                "model": self.model, "estimated_prompt_tokens": None, "prompt_tokens": tokens[0],
                "cache_hit_tokens": tokens[2] or 0, "completion_tokens": tokens[1], "reasoning_tokens": None,
                "cost_usd": cost, "request_id": None})
