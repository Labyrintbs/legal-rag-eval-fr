"""Harness sanity check on BSARD (22,633 Belgian statutory articles, 222 test questions with
article-level relevance): bge-m3 with the same metric code as the main evaluation, no database.

BSARD is CC BY-NC-SA 4.0: the files and the vectors stay outside git. Embedding runs in blocks that
are saved as they finish, so an interrupted run resumes. See docs/handoff/bsard_windows.md.
"""

import argparse
import csv
import hashlib
import json
import urllib.request
from pathlib import Path

import numpy as np

from legalrag import metrics
from legalrag.embed import MAX_SEQ_LENGTH, SentenceTransformerEmbedder

REVISION = "f3ca6a396a47c4a3afd26b766b5abc0a56bb4205"  # dataset revision the checksums were taken from
URL = "https://huggingface.co/datasets/maastrichtlawtech/bsard/resolve/" + REVISION + "/{name}"
FILES = {
    "articles.csv": "8bbc68453638f446ad35647d61ba271a8fbea481ae5b3de761c84f71ba30deb6",
    "questions_test.csv": "2607fff3deab14a2b915366b49674cb9fde35fabdbc9d41be0aa193dfaef37c8",
}
TOP = 500  # the paper reports Recall@100/200/500
RECALL_KS = (100, 200, 500)
BLOCK = 2000
SMOKE_QUESTIONS, SMOKE_ARTICLES = 10, 300
QUERY_VARIANTS = ("question", "question + extra_description")


def fetch(data: Path) -> None:
    data.mkdir(parents=True, exist_ok=True)
    for name, expected in FILES.items():
        target = data / name
        if not target.exists():
            part = target.with_name(name + ".part")
            urllib.request.urlretrieve(URL.format(name=name), part)
            part.replace(target)
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit(f"{name}: sha256 {actual} differs from {expected}")
        print(f"{name}: ok")


def read_csv(path: Path) -> list[dict]:
    csv.field_size_limit(10**9)
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def smoke_subset(articles: list[dict], questions: list[dict]) -> tuple[list[dict], list[dict]]:
    """First questions, their gold articles, then the first other articles up to SMOKE_ARTICLES."""
    questions = questions[:SMOKE_QUESTIONS]
    wanted = {i for q in questions for i in q["article_ids"].split(",")}
    kept = [a for a in articles if a["id"] in wanted]
    kept += [a for a in articles if a["id"] not in wanted][: SMOKE_ARTICLES - len(kept)]
    return kept, questions


def embed_blocks(embedder, texts: list[str], folder: Path) -> np.ndarray:
    folder.mkdir(parents=True, exist_ok=True)
    parts = []
    for start in range(0, len(texts), BLOCK):
        path = folder / f"block_{start // BLOCK:04d}.npy"
        if not path.exists():
            vectors = np.asarray(embedder.encode(texts[start:start + BLOCK], 16), dtype=np.float32)
            np.save(path.with_name(path.name + ".part.npy"), vectors.astype(np.float16))
            path.with_name(path.name + ".part.npy").replace(path)
            print(f"embedded {min(start + BLOCK, len(texts))}/{len(texts)}", flush=True)
        parts.append(np.load(path).astype(np.float32))
    return np.concatenate(parts)


def unit(vectors: np.ndarray) -> np.ndarray:
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def query_text(q: dict, variant: str) -> str:
    return q["question"] if variant == QUERY_VARIANTS[0] else f"{q['question']} {q['extra_description']}".strip()


def evaluate(article_ids: list[str], doc_vecs: np.ndarray, query_vecs: np.ndarray, questions: list[dict]) -> dict:
    order = np.argsort(-(query_vecs @ doc_vecs.T), axis=1)[:, :TOP]
    rows = []
    for q, top in zip(questions, order, strict=True):
        gold = [(i, i, metrics.PRIMARY) for i in q["article_ids"].split(",")]
        matched = metrics.match_ranking([(article_ids[j], article_ids[j]) for j in top], gold)
        rows.append({**metrics.question_metrics(matched),
                     **{f"recall@{k}": metrics.recall_at(matched, k) for k in RECALL_KS}})
    names = list(rows[0])
    clusters = [q["id"] for q in questions]  # no known grouping of related questions
    return {name: metrics.bootstrap_ci([r[name] for r in rows], clusters) for name in names}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/external/bsard"))
    parser.add_argument("--out", type=Path, default=Path("data/external/bsard_out"))
    parser.add_argument("--device", default="auto")
    parser.add_argument("--smoke", action="store_true", help="10 questions and 300 articles, to check the setup")
    parser.add_argument("--no-fetch", action="store_true", help="files are already in --data")
    args = parser.parse_args()

    if not args.no_fetch:
        fetch(args.data)
    articles = read_csv(args.data / "articles.csv")
    questions = read_csv(args.data / "questions_test.csv")
    if args.smoke:
        articles, questions = smoke_subset(articles, questions)
    out = args.out / ("smoke" if args.smoke else "full")

    embedder = SentenceTransformerEmbedder(args.device)
    texts = [f"{a['reference']}\n{a['article']}" for a in articles]
    too_long = sum(len(ids) + 2 > MAX_SEQ_LENGTH for ids in embedder.model.tokenizer(texts)["input_ids"])
    doc_vecs = unit(embed_blocks(embedder, texts, out / "blocks"))
    article_ids = [a["id"] for a in articles]
    (out / "article_ids.json").write_text(json.dumps(article_ids))

    results = {}
    for variant in QUERY_VARIANTS:
        vectors = np.asarray(embedder.encode([query_text(q, variant) for q in questions], 16), dtype=np.float32)
        results[variant] = evaluate(article_ids, doc_vecs, unit(vectors), questions)
    summary = {
        "articles": len(articles), "questions": len(questions), "articles_truncated": too_long,
        "dataset_revision": REVISION, "embedder": embedder.info(), "smoke": args.smoke,
        "document_text": "reference, line break, article", "search": "dense, exact cosine, top 500",
        "bootstrap": "2000 resamples of questions, 95% percentile interval",
        "metrics": {v: {n: list(t) for n, t in r.items()} for v, r in results.items()},
    }
    (out / "results.json").write_text(json.dumps(summary, indent=1))
    print(f"{len(articles)} articles ({too_long} truncated), {len(questions)} questions")
    for variant, scores in results.items():
        print(f"\nquery = {variant}")
        for name, (mean, low, high) in scores.items():
            print(f"  {name:11s} {mean:.3f} [{low:.3f}-{high:.3f}]")


if __name__ == "__main__":
    main()
