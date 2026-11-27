# Code map

The code is in folders by job. A module may import from its own folder and from the folders above it in this list, never
from the ones below: `corpus` < `index` < `answering` < `experiments` < `evaluation` < `web` < `cli`. Shared helpers go to the
lowest folder that needs them (`corpus/labels.py`, `corpus/text.py`, `index/embed.py`). `llm.py` (the model client, the price
table, the provider settings read from the environment, and the spend ledger) sits beside them and imports nothing from the folders.

`tests/` and `scripts/` have the same folders. Put a new module where its job is; if no folder fits, say so before adding one.

## `src/legalrag/`

| Folder | Job | Modules |
|---|---|---|
| `corpus/` | the texts: fetch, parse, check, cut into chunks | `fetch`, `sources/` (`legi`, `gdpr`), `models`, `text`, `labels`, `verify`, `chunking/` (`header`, `split`), `ingest`, `variants` |
| `index/` | vectors and the database | `config`, `db`, `store`, `dbcheck`, `embed` |
| `answering/` | what a request to the service goes through | `search`, `units`, `answer`, `rag` (the LlamaIndex layer), `articlenum`, `limits`, `trace`, `logs`, `cache` (the answer cache), `pii` (the personal-data filter) |
| `experiments/` | the step 0c options that are not in the final setup; frozen: kept with their tests because `EXPERIMENT.md` and the decisions refer to them, and not extended | `rerank`, `rewrite`, `sparse`, `keyword`, `headsentence` |
| `evaluation/` | measuring: gold, metrics, judges, outside datasets | `gold`, `goldjudge`, `draw`, `questiongen`, `metrics`, `evaluate`, `smoke`, `sanity`, `answermetrics`, `claimjudge`, `labelsheet`, `claimrag`, `citationcompare`, `cifixture`, `answer_relevance`, `ministry`, `judgecall` |
| `web/` | the HTTP service (step 0f): the API and its reply shapes, answering one question (cache, engine, traces), the cache warm-up, and the real wiring; `static/` holds the demo pages (question page, history, method, data, privacy) and their scripts (`texts_en.js`, `history.js`, `mail.js`, then `app.js`, which starts the page), tested in QuickJS | `app`, `schemas`, `asking`, `warm`, `examples`, `build` |
| `cli/` | the `legalrag` command, one module per job | `corpus`, `index`, `evaluation`, `service`, and `common` (paths and helpers they share) |
| top level | the model client | `llm` |

## `tests/` and `scripts/`

`tests/<folder>/test_<module>.py` for the modules above (`tests/web/` needs the serve extra); `tests/gate/` is the quality gate of CI (step 0e, see `docs/decisions/0007-step-0e-quality-gate.md`); `tests/test_repository.py` (nothing forbidden tracked, the code map and the README agree with the code), `tests/conftest.py` (database fixtures, and skips fail in CI) and `tests/fixtures/` stay at
the top, and `tests/test_llm.py` tests `llm.py`.

| `scripts/` folder | Holds |
|---|---|
| `evalset/` | building the question set and its gold lists |
| `answers/` | the answer pilots, judging, metrics and the hand-labelling sheets |
| `data/` | data preparation and the Releases (`pack_*`, `fresh_rebuild`, fixtures, heading sentences) |
| `benchmarks/` | the outside sanity runs (BSARD, Syntec) |

## Deployment files (at the top, not code)

| File | Holds |
|---|---|
| `Dockerfile`, `.dockerignore` | the server image: CPU torch, non-root user, no data, weights in a volume |
| `compose.server.yaml` | the server stack (proxy, app, database); `docker-compose.yml` is the development database |
| `deploy/nginx.conf` | the proxy: size and time limits, the visitor-address header, no access log |
| `deploy/deploy.sh`, `deploy/backup.sh` | on the server: build, start, provider check, rollback; nightly encrypted backup of the non-personal tables and the settings, with a restore drill |
| `OPERATIONS.md` | how to run it: first start, settings, kill switch, upkeep, backups, checks from outside |
| `.github/workflows/ci.yml` | checks, quality gate, secret scan, audit, and the image build with its checks |

## Where the old files went (2026-11-10)

`EXPERIMENT.md` and the decision files keep the old names, as written at the time.

| Old | New |
|---|---|
| `src/legalrag/{fetch,models,text,ingest,variants,verify}.py`, `chunking/`, `sources/` | `src/legalrag/corpus/...` |
| `src/legalrag/smoke.py` (`article_label`, `split_label`) | `src/legalrag/corpus/labels.py` |
| `src/legalrag/smoke.py` (`EF_SEARCH`), `embed_questions` | `index/store.py` (`EF_SEARCH`), `index/embed.py` (`embed_queries`); `evaluation/smoke.py` keeps the rest |
| `src/legalrag/questiongen.py` (`context_of`) | `corpus/text.py` |
| `src/legalrag/{config,db,dbcheck,store,embed}.py` | `src/legalrag/index/...` |
| `src/legalrag/{search,units,answer,rag,limits,trace,logs,articlenum}.py` | `src/legalrag/answering/...` |
| `src/legalrag/{rerank,rewrite,sparse,keyword,headsentence}.py` | `src/legalrag/experiments/...` |
| `src/legalrag/{gold,goldjudge,draw,questiongen,metrics,evaluate,smoke,sanity,answermetrics,claimjudge,labelsheet,claimrag,citationcompare}.py` | `src/legalrag/evaluation/...` |
| `src/legalrag/cli.py` | `src/legalrag/cli/{corpus,index,evaluation,service,common}.py` |
| `scripts/build_gold, draw_articles, write_questions, pilot_questions, reviewer_eval, rewrite_questions, judge_gold` | `scripts/evalset/` |
| `scripts/answer_pilot, citation_pilot, answer_metrics, claimrag_english, claimrag_judge, judge_claims, make_label_sheet, make_completeness_sheet` | `scripts/answers/` |
| `scripts/pack_variants, pack_sparse, heading_sentence_pilot, heading_sentences_all, fresh_rebuild, make_fixture, make_gdpr_fixture` | `scripts/data/` |
| `scripts/sanity_bsard, sanity_syntec` | `scripts/benchmarks/` |
| `tests/test_<module>.py` | `tests/<folder>/test_<module>.py` |
