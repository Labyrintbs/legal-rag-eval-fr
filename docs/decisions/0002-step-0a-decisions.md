# Decisions of step 0a (ingest, storage, first retrieval)

Written 2026-10-27, after the Loop 3 and Loop 4 gates were approved. Each row says what was decided, by whom, and where the evidence is. The database design has its own note: `0001-database-design.md`.

## Scope and setup

| Decision | Who, when | Evidence |
|---|---|---|
| Corpus: Code du travail and GDPR (French as the main text, English also ingested). Recitals are their own chunks. | User, 2026-10-20 | `docs/data_profiles/` |
| Questions in French first; Code du travail built before the GDPR | User, 2026-10-20 | plan memory (P3, P6) |
| Repository public, no code licence; attribution in `NOTICE.md` | User, 2026-10-20 | `NOTICE.md` |
| Tooling: uv, pyproject, ruff, pytest, Alembic, psycopg 3, pydantic, typer | User, 2026-10-20 | `pyproject.toml` |
| Every change to data processing or chunking is logged with its measured effect; push to GitHub after every commit | User, 2026-10-20 | `EXPERIMENT.md`, `CLAUDE.md` |
| Vectors are computed on the user's Windows GPU laptop and shared only as GitHub Release assets, never in git | User, 2026-10-21 and 2026-10-22 | `EXPERIMENT.md` (Loop 3 entries), release `embeddings-bge-m3-main-v1` |

## Chunking

| Decision | Who, when | Evidence |
|---|---|---|
| One article is one chunk; split only above 1,024 bge-m3 tokens (header included); no overlap | Plan, confirmed | `EXPERIMENT.md` 2026-10-20 |
| Code du travail splits at sentences; GDPR at paragraphs, then points, then sentences; a last-resort cut by words is flagged on the chunk | Plan, confirmed | `chunking/split.py`, `ingest.py`; known limits in `EXPERIMENT.md` 2026-10-24 |
| Heading line: code, article number, last 3 section levels (`last_k`, k=3) | Plan, confirmed | `chunking/header.py` |
| `section_path` stored as in the source; whitespace cleaned only when the heading is built | User, 2026-10-20 | `EXPERIMENT.md` 2026-10-20 |
| "Collapse repeated levels" exists and is off. It reproduces the Légifrance path in 28 of 28 checked articles; its effect on retrieval is tested in 0c | User, 2026-10-20 | `tests/fixtures/legifrance_site_paths.json` |
| Annexes stay searchable; compared with excluding them in 0c | User, 2026-10-20 | `EXPERIMENT.md` 2026-10-20 |

## Embeddings and database

| Decision | Who, when | Evidence |
|---|---|---|
| BAAI/bge-m3, dense, 1,024 dimensions, fp16 on GPU, vectors normalised; queries without an instruction prefix | Plan; prefix rule from the model card | `EXPERIMENT.md` 2026-10-22, 2026-10-27 |
| Chunk identity across machines: (`article_uid`, `chunk_index`) plus the SHA-256 of `embed_text`; a vector whose hash differs from the stored chunk is refused | Design | `embed.py`, `store.py` |
| Postgres 16 with pgvector 0.8.7 in Docker; schema with five tables; chunking runs are immutable | User accepted, 2026-10-22 | `0001-database-design.md` |
| Migration `0002`: `lang` limited to fr/en, `kind` to article/recital/annex, deleting a chunking run deletes its chunks; `legalrag delete-run` asks first | User, 2026-10-26 | `EXPERIMENT.md` 2026-10-26 |
| `valid_to` keeps the source value (2999-01-01 in the Code du travail, NULL in the GDPR); decided again when a query first filters on dates | User, 2026-10-26 | `0001-database-design.md` |
| `load-chunks` refuses a git tree with uncommitted changes, so a stored run names its exact code | User, 2026-10-24 | `EXPERIMENT.md` 2026-10-24 |
| `ANALYZE` after loading the vectors | Found by the first rebuild | `EXPERIMENT.md` 2026-10-26 |

## Checks and first retrieval

| Decision | Who, when | Evidence |
|---|---|---|
| `db-check` has 11 checks. The cross-language check (10) uses an exact search; the index recall check (11) is known to be optimistic for real questions and is left as it is | User, 2026-10-26 and 2026-10-27 | `EXPERIMENT.md` 2026-10-26, 2026-10-27 |
| `make fresh-rebuild` rebuilds into a scratch database and compares it with the real one | User, 2026-10-26 | `scripts/fresh_rebuild.py` |
| Smoke retrieval: 29 hand-written questions in 7 groups, nearest 5 chunks, query-time `hnsw.ef_search` 100; an inspection, not a metric | User, 2026-10-26 and 2026-10-27 | `tests/smoke_questions.yaml`, `docs/data_profiles/smoke_notes.md` |

## Result of 0a

All the exit conditions of the spec are met: a fresh rebuild works from the raw files and the Release (all fingerprints equal); checks pass; the test suite passes; data profiles and spot checks are committed; vectors exist for all 12,136 chunks and the index is built; the smoke output was reviewed with the user; the README states the corpus dates and the disclaimer; the user approved Loops 1 to 4.

## Open points carried forward

| Point | Where it goes |
|---|---|
| Keyword search method; French stemming of plurals (`démission` and `démissions` get different roots) | 0c |
| Header variants: none, label only, last k, full path, collapse repeated levels; header effect seen on two questions (Q3, Q8) | 0c |
| Annexes: as they are, excluded, or summarised | 0c |
| Chunk size 1,024 against 512; overlap | 0c |
| Language: a filter, or French and English as one unit; the index only searches a short candidate list before it applies a filter | 0c |
| Query-time `ef_search`, or exact search for evaluation | 0b and 0c |
| Gold answers with a primary article and also-acceptable ones (Q16, Q20, Q21 of the smoke set) | 0b |
| Index recall check built on stored vectors | revisit when the evaluation code exists |
| Licences of benchmark data (BSARD: CC BY-NC-SA 4.0; Syntec and ClaimRAG-LAW: none found) | 0b, before publishing numbers |
| CI needs a Postgres service; the database tests skip without one | 0e |
