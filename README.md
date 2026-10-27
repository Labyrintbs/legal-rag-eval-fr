# legal-rag-eval-fr

Question answering over French labour law (Code du travail) and the GDPR, with measured evaluation. French questions first. Answers will cite articles and refuse when the corpus cannot answer.

**Status:** step 0a (ingest, storage, first retrieval) is done. The evaluation set (0b) is next. There is no answer generation and nothing is deployed.

**Disclaimer:** legal information, not legal advice. The corpus has a date (below) and may not contain the current law.

## Corpus

| Source | Content | Date |
|---|---|---|
| Code du travail | Community extract `VinceGx33/legi-french-law-2025` of the official DILA/LEGI dump. In-force articles only: 11,433 rows | Snapshot of 2025-07-13 |
| GDPR (Regulation (EU) 2016/679) | French and English text from the EU Publications Office: 99 articles, 173 recitals, 11 chapters, 15 sections per language | Official Journal L 119 of 2016-05-04; later corrigenda not checked |

An article that changed after the snapshot is stored in its older form (one example found: L6123-5, in force since 2026-02-21 on Légifrance, 2024-01-01 in the data). Attribution and licences: [NOTICE.md](NOTICE.md).

What is stored: 11,977 articles and recitals in 12,136 chunks. One article is one chunk unless it exceeds 1,024 bge-m3 tokens; each chunk starts with a heading line (code, article, last 3 section levels). Vectors: BAAI/bge-m3, 1,024 dimensions, in Postgres 16 with pgvector and a cosine HNSW index. Keyword-search columns exist but no keyword search is used yet.

## Setup

Needs Docker, [uv](https://docs.astral.sh/uv/) and `gh`.

```
uv sync
make fetch                 # raw data into data/raw/ (gitignored), SHA-256 verified
make db-up
make migrate               # tables, constraints (DATABASE_URL, default: the compose database)
make load-chunks           # needs a clean git tree
gh release download embeddings-bge-m3-main-v1 -D data/embeddings
make load-embeddings       # loads the vectors, builds the index, runs ANALYZE
make db-check              # 11 checks on what is stored
make test
```

The vectors are shared as a GitHub Release asset and are never committed. To recompute them you need a GPU: `make embed` (see `docs/handoff/loop3_windows_embedding.md`).

`make fresh-rebuild` rebuilds everything from the raw files and the Release into a scratch database, compares it with your database, and drops it.

## Commands

| Command | What it does |
|---|---|
| `make fetch` | Download the raw files and check their checksums |
| `make profile SOURCE=legi\|gdpr`, `make verify SOURCE=legi\|gdpr` | Data profile and checks per source |
| `make embed`, `make sanity` | Compute the vectors, and a quick check of them (GPU recommended) |
| `make migrate`, `make load-chunks`, `make load-embeddings` | Build the database |
| `make db-check` | 11 checks: counts, vectors, hashes, index use, cross-language match, index recall |
| `make smoke` | 29 hand-written questions, nearest 5 chunks each (needs the `embed` extra: PyTorch) |
| `make llm-balance`, `make llm-ledger` | DeepSeek balance snapshot (needs `DEEPSEEK_API_KEY` in `.env`) and the cost ledger of the question-writing calls |
| `legalrag delete-run NAME` | Delete a chunking run with its chunks and vectors (asks first) |
| `make fresh-rebuild` | Rebuild from nothing into a scratch database and compare |

## First retrieval results

`make smoke` (dense search only, no keyword search, no reranker): the expected article is in the top 5 for 23 of 27 questions that have one. Failures: a question in everyday words for the rupture conventionnelle, an exact article number, a table inside an annex, and the territorial scope of the GDPR. Details and the reading of every result: [docs/data_profiles/smoke_notes.md](docs/data_profiles/smoke_notes.md). This is an inspection of 29 questions, not a measured score; the evaluation set comes in step 0b.

## Known limits

- Dense search only; the French stemmer of Postgres maps "démission" and "démissions" to different roots, which matters once keyword search is added.
- Long annexes (flattened tables) are split into many chunks and are hard to find by a detail inside.
- French and English GDPR chunks share one index; a French question gets English copies in its top 5.
- The vector index is approximate. With the default `hnsw.ef_search` of 40 it missed a correct article in one smoke question; the smoke command uses 100.
- No answer generation, no refusal rule, no reranker yet.

## Where things are

- [EXPERIMENT.md](EXPERIMENT.md): every change to data processing and chunking, and the measurements, newest last.
- [docs/decisions/](docs/decisions/): design decisions (database design, decisions of step 0a).
- [docs/data_profiles/](docs/data_profiles/): statistics and spot checks of each source, smoke notes.
- `src/legalrag/`: `sources/` (readers), `chunking/` (headers, splitting), `ingest.py`, `embed.py`, `store.py`, `dbcheck.py`, `smoke.py`, `cli.py`. Migrations in `migrations/`, tests in `tests/`.
- [CLAUDE.md](CLAUDE.md): rules for working with the AI assistant on this repo.
