"""Harness sanity check on Syntec (90 articles of a collective agreement, 100 French questions, one
gold article each): the same metric code and embedding model as the main evaluation, no database.

Syntec files are read from --data and never copied into the repo (licence unknown).
"""

import argparse
import json
from pathlib import Path

import numpy as np

from legalrag import metrics
from legalrag.embed import SentenceTransformerEmbedder

TOP = 20


def load(data: Path) -> tuple[list[dict], list[dict]]:
    return json.loads((data / "documents.json").read_text()), json.loads((data / "queries.json").read_text())


def rank_all(embedder, docs: list[dict], queries: list[dict]) -> list[list[str]]:
    """Article ids by dense similarity (cosine, exact), best first, for each query."""
    texts = [f"{d['title']}\n{d['content']}" for d in docs]
    doc_vecs = np.asarray(embedder.encode(texts, 8), dtype=np.float32)
    query_vecs = np.asarray(embedder.encode([q["Question"] for q in queries], 16), dtype=np.float32)
    doc_vecs /= np.linalg.norm(doc_vecs, axis=1, keepdims=True)
    query_vecs /= np.linalg.norm(query_vecs, axis=1, keepdims=True)
    order = np.argsort(-(query_vecs @ doc_vecs.T), axis=1)[:, :TOP]
    return [[docs[i]["id"] for i in row] for row in order]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True, help="folder with documents.json and queries.json")
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()

    docs, queries = load(args.data)
    embedder = SentenceTransformerEmbedder(args.device)
    rankings = rank_all(embedder, docs, queries)
    rows = []
    for q, ranked in zip(queries, rankings, strict=True):
        matched = metrics.match_ranking([(a, a) for a in ranked], [(q["Article"], q["Article"], metrics.PRIMARY)])
        rows.append(metrics.question_metrics(matched))
    clusters = [q["Article"] for q in queries]  # questions on one article are not independent
    print(f"{len(queries)} questions, {len(set(clusters))} clusters, {len(docs)} articles; model {embedder.info()['model']}")
    for name in metrics.METRICS:
        mean, low, high = metrics.bootstrap_ci([r[name] for r in rows], clusters)
        print(f"{name:10s} {mean:.3f} [{low:.3f}-{high:.3f}]")


if __name__ == "__main__":
    main()
