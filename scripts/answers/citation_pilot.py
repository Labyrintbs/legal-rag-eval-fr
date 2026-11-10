"""LlamaIndex's own CitationQueryEngine on the 65 dev questions (decision 5 of 0006): the same retrieval (our
`LegalRetriever`), the same weak-retrieval check, the same model; the engine's default prompt and its own
512-token source chunks. Its answer is converted to the rows of `answer_pilot.py`, so that
`answer_metrics.py --tag <tag>` scores it with the same judge.
  uv run --extra serve --extra embed python scripts/citation_pilot.py --model deepseek-flash --tag citation
"""

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from llama_index.core.instrumentation import get_dispatcher
from llama_index.core.instrumentation.event_handlers import BaseEventHandler
from llama_index.core.instrumentation.events.llm import LLMChatEndEvent, LLMCompletionEndEvent
from llama_index.core.query_engine import CitationQueryEngine
from llama_index.core.schema import QueryBundle
from llama_index.llms.deepseek import DeepSeek
from pydantic import Field

from legalrag import llm
from legalrag.answering import answer, rag, search
from legalrag.evaluation import citationcompare, gold
from legalrag.index import db, embed

RUN = "default"  # the chunking run of the pilot
PILOT = Path("data/pilot")


class UsageHandler(BaseEventHandler):
    """Collects the token usage of every model call the engine makes: (in, out, cached) per call."""

    calls: list = Field(default_factory=list)

    @classmethod
    def class_name(cls) -> str:
        return "UsageHandler"

    def handle(self, event, **kwargs) -> None:
        if isinstance(event, LLMChatEndEvent | LLMCompletionEndEvent):
            raw = event.response.raw
            usage = raw.get("usage") if isinstance(raw, dict) else getattr(raw, "usage", None)
            self.calls.append(answer.usage_of(SimpleNamespace(**usage) if isinstance(usage, dict) else usage))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--n", type=int, default=None, help="trial: only the first N dev questions")
    parser.add_argument("--threshold", type=float, default=search.WEAK_THRESHOLD, help="0 switches the pre-filter off")
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()

    questions = [q for q in gold.load_gold(Path("eval/gold.jsonl")) if q.split == "dev" and q.lang == "fr"][: args.n]
    model = DeepSeek(model=args.model, api_key=os.environ["DEEPSEEK_API_KEY"], temperature=0,
                     additional_kwargs={"extra_body": {"thinking": {"type": "disabled"}}}, max_tokens=700)
    with db.connect() as conn:
        run_id = conn.execute("SELECT id FROM chunking_runs WHERE name = %s", (RUN,)).fetchone()[0]
    retriever = rag.LegalRetriever(db.connect, run_id, embed.SentenceTransformerEmbedder(args.device), "fr")
    engine = CitationQueryEngine(retriever=retriever, llm=model)
    handler = UsageHandler()
    get_dispatcher().add_event_handler(handler)

    rows = []
    for q in questions:
        started = time.monotonic()
        nodes = retriever.retrieve(q.question)
        hits = rag.hits_of(nodes)
        row = {"id": q.id, "kind": q.kind, "gold": [g.article for g in q.gold],
               "primary": [g.article for g in q.gold if g.grade == 2], "top5": [h.label for h in hits],
               "top_similarity": hits[0].similarity if hits else None, "cited": [], "text": "", "uncited_sentences": 0,
               "tokens_in": None, "tokens_out": None, "cost_usd": None, "llm_ms": None, "error": None, "reason": None}
        if search.is_weak(hits, args.threshold):
            row |= {"outcome": "refused_weak_retrieval", "text": "(no answer: nothing close enough found)"}
        else:
            handler.calls.clear()
            asked = time.monotonic()
            try:
                response = engine.synthesize(QueryBundle(q.question), nodes)
            except Exception as error:  # noqa: BLE001 - any failure of the call is recorded, as in the answer path
                row |= {"outcome": "llm_error", "error": type(error).__name__}
            else:
                row["llm_ms"] = round((time.monotonic() - asked) * 1000)
                sources = [(n.node.metadata["label"], citationcompare.source_passage(n.node.text)) for n in response.source_nodes]
                cited, row["uncited_sentences"] = citationcompare.cited_sentences(str(response), len(sources))
                row["raw"] = str(response)
                tokens_in = sum(c[0] or 0 for c in handler.calls)
                tokens_out = sum(c[1] or 0 for c in handler.calls)
                cached = sum(c[2] or 0 for c in handler.calls)
                cost = llm.cost_usd(args.model, cached, tokens_in - cached, tokens_out, datetime.now(UTC))
                row |= {"tokens_in": tokens_in, "tokens_out": tokens_out, "cost_usd": cost}
                if cited:
                    row |= {"outcome": "answered", "text": citationcompare.render(cited, sources),
                            "cited": sorted({sources[n - 1][0] for _, numbers in cited for n in numbers})}
                else:
                    row |= {"outcome": "refused_by_model", "text": str(response), "reason": "no sentence cites a source"}
        row["total_ms"] = round((time.monotonic() - started) * 1000)
        rows.append(row)

    PILOT.mkdir(parents=True, exist_ok=True)
    path = PILOT / f"answers_{args.tag}.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    print(f"model {args.model}, CitationQueryEngine, threshold {args.threshold}, {len(rows)} questions, written to {path}")


if __name__ == "__main__":
    main()
