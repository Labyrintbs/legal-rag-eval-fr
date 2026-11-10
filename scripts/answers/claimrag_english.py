"""The English GDPR questions of ClaimRAG-LAW (the 66 questions of the claim file that have a source text) through our
answer path, in two setups, scored by the judges of decisions 16 and 19:
  oracle: the dataset's source text is the only source (no search): the answering with perfect context;
  full:   our search over the English corpus, then the answer (the whole pipeline).
Metrics: faithfulness (`judge.v2`), citations and refusals, completeness against the expert-entailed reference claims
(`judge.v3`, indicative), and for `full` the retrieval of the gold articles (`claimrag.gold_labels`, 30% overlap).
Spends model money (about 0.1 USD per setup).
  uv run --extra serve --extra embed python scripts/claimrag_english.py --mode both
"""

import argparse
import json
import os
from pathlib import Path

from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, TextNode
from llama_index.llms.deepseek import DeepSeek

from legalrag.answering import rag, search
from legalrag.corpus.labels import article_label
from legalrag.evaluation import answermetrics, claimjudge, claimrag
from legalrag.evaluation import questiongen as qg
from legalrag.index import db, embed

DATA = Path("data/claimrag")
RUN = "default"  # the chunking run
JUDGE_PROMPT = "judge.v2"
COMPLETENESS_PROMPT = "judge.v3"


class ChunkRetriever(BaseRetriever):
    """Always the same source text, as one article: the answering with perfect context."""

    def __init__(self, chunk: str) -> None:
        super().__init__()
        self.chunk = chunk

    def _retrieve(self, query_bundle):
        node = TextNode(id_="claimrag#0", text=self.chunk, metadata={
            "label": "source text", "chunk_index": 0, "header": "", "section_path": "", "url": ""})
        return [NodeWithScore(node=node, score=1.0)]


def english_articles() -> list[tuple[str, str]]:
    """(label, text) of every English GDPR article and recital of the corpus."""
    with db.connect() as conn:
        rows = conn.execute("SELECT source_code, kind, article_num, body_text FROM articles "
                            "WHERE lang = 'en' AND source_code = 'rgpd'").fetchall()
    return [(article_label(source, kind, num), text) for source, kind, num, text in rows]


def ask(engine: rag.AnswerEngine, question: claimrag.Question, gold: list[str]) -> dict:
    result = engine.respond(question.text).metadata["result"]
    cited = sorted({c.label for _, cs in (result.resolved.claims if result.resolved else []) for c in cs})
    return {"id": question.id, "question": question.text, "kind": question.kind, "outcome": result.outcome,
            "text": result.text, "cited": cited, "gold": gold, "primary": gold, "top5": [h.label for h in result.hits],
            "top_similarity": result.hits[0].similarity if result.hits else None, "reference_claims": question.reference_claims,
            "tokens_in": result.tokens_in, "tokens_out": result.tokens_out, "cost_usd": result.cost_usd,
            "llm_ms": result.llm_ms, "total_ms": result.total_ms, "reason": result.reason}


def judge(items: list[claimjudge.Item], model: str, prompt_id: str, tag: str) -> list[dict]:
    """The verdicts, also written to data/judge/<tag>.jsonl so that each one can be read."""
    verdicts = claimjudge.run_judge(items, model, False, 0.5, 6, tag, prompt_id)
    Path("data/judge").mkdir(parents=True, exist_ok=True)
    Path(f"data/judge/{tag}.jsonl").write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in verdicts))
    return verdicts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=("oracle", "full", "both"), default="both")
    parser.add_argument("--model", default="deepseek-flash")
    parser.add_argument("--answer-prompt", default="answer.v3")
    parser.add_argument("--n", type=int, default=None, help="trial: only the first N questions")
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()

    questions = claimrag.load_questions(DATA / "GDPR-CLAIM-LAW.json", DATA / "GDPR-RAG-LAW.json")[: args.n]
    articles = english_articles()
    gold = {q.id: claimrag.gold_labels(q.chunk, articles) for q in questions}
    prompt = qg.load_prompts(Path("prompts/answer.yaml"))["prompts"][args.answer_prompt]
    model = DeepSeek(model=args.model, api_key=os.environ["DEEPSEEK_API_KEY"], temperature=0,
                     additional_kwargs={"extra_body": {"thinking": {"type": "disabled"}}}, max_tokens=prompt["max_tokens"])
    with db.connect() as conn:
        run_id = conn.execute("SELECT id FROM chunking_runs WHERE name = %s", (RUN,)).fetchone()[0]
    embedder = embed.SentenceTransformerEmbedder(args.device)
    print(f"{len(questions)} questions; gold list sizes {sorted({len(g) for g in gold.values()})}")

    for mode in ("oracle", "full") if args.mode == "both" else (args.mode,):
        rows = []
        for q in questions:
            retriever = ChunkRetriever(q.chunk) if mode == "oracle" else rag.LegalRetriever(db.connect, run_id, embedder, "en")
            engine = rag.AnswerEngine(retriever=retriever, postprocessor=rag.NumberUnits(), llm=model, prompt=prompt,
                                      model=args.model, prompt_id=args.answer_prompt, threshold=search.WEAK_THRESHOLD,
                                      ledger_label=f"claimrag-english-{mode}")
            rows.append(ask(engine, q, gold[q.id]))
        (DATA / f"answers_{mode}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        faithfulness = judge(answermetrics.claim_items(rows), args.model, JUDGE_PROMPT, f"claimrag-english-{mode}-faith")
        completeness = judge(claimrag.completeness_items(rows), args.model, COMPLETENESS_PROMPT,
                             f"claimrag-english-{mode}-complete")
        result = {"mode": mode, "questions": len(rows), "faithfulness": answermetrics.faithfulness(faithfulness),
                  "citations": answermetrics.citations(rows), "refusals": answermetrics.refusals(rows),
                  "passages": answermetrics.passages(rows), "completeness": claimrag.completeness(rows, completeness),
                  "retrieval": claimrag.retrieval(rows) if mode == "full" else None, "cost": answermetrics.cost(rows)}
        (DATA / f"results_{mode}.json").write_text(json.dumps(result, indent=1) + "\n")
        print(f"\n== {mode}\n{json.dumps(result, indent=1)}")


if __name__ == "__main__":
    main()
