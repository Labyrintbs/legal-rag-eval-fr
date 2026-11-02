# Decisions of step 0c (retrieval experiments)

Started 2026-10-29. Every run is compared with the dense baseline on the dev half using the paired difference and the guardrail of decision 3b in `0003-step-0b-decisions.md`. The test half is opened once, at the end of the stage.

| # | Decision | Who, when |
|---|---|---|
| 1 | Experiment A (keyword search): BM25 on the lexemes Postgres stores in `chunks.tsv`, alone and fused with dense by reciprocal rank fusion (k 60, top 100 articles each, optional weight on the keyword list). No setting is an improvement on dev (`EXPERIMENT.md` 2026-10-29), so dense stays the retrieval default | Assistant result, to confirm |
| 2 | Chunking variants (header none, label, full path, collapsed repeats; 512-token limit) are embedded on the Windows laptop and shared as the Release `embeddings-bge-m3-variants-v1` (`docs/handoff/variants_windows.md`). Overlap between chunks is not implemented and is not tried | User, 2026-10-29 |

## Planned ablations (source: the master plan of 2026-10-20, decisions D6, D7, P5, E4, and the 0a open items)

Written here on 2026-10-29; before that the list existed only in the master plan outside this repository. One change at a time, same eval set, dev half; keep only what helps.

| Ablation | What is compared | Needs new embeddings | Status |
|---|---|---|---|
| Dense baseline | bge-m3, heading `last_k` k=3, 1,024-token limit | no | done, nDCG@10 0.738 |
| Keyword search and rank fusion | BM25 over Postgres lexemes alone and fused with dense (weights 1, 0.5, 0.25); Postgres `ts_rank` done (`EXPERIMENT.md` 2026-11-03): alone nDCG@10 -0.312 and -0.246 (length-normalised) against dense, fused -0.003 to -0.064, worse than BM25, no improvement; bge-m3 sparse code ready, waiting for the laptop vectors (`docs/handoff/bge_sparse_windows.md`) | no | done for BM25, no improvement |
| Reranker | bge-reranker-v2-m3 against Qwen3-Reranker-0.6B against none, with CPU latency per question (P5); Jina excluded (CC-BY-NC) | no | done on dev after three faults were fixed (`EXPERIMENT.md` 2026-10-31): bge-reranker-v2-m3 (top 50) nDCG@10 +0.055 [-0.006, +0.120], not an improvement by 3b; Qwen3-Reranker-0.6B +0.061 [+0.003, +0.125], an improvement by 3b with a lower bound barely above 0; the two are not distinguishable (+0.006). CPU time per question 36 s (bge) and 91 s (Qwen, swapping Mac, upper bound); dense 0.3 to 0.4 s. Matrix with Qwen3-Embedding candidates: bge-reranker +0.062 [-0.002, +0.128], Qwen3-Reranker +0.054 [-0.004, +0.120], neither an improvement; only bge-m3 with Qwen3-Reranker passes 3b, barely (`EXPERIMENT.md` 2026-10-31, full matrix). Default stays dense bge-m3 without reranker (user agreed 2026-10-31). Candidate depth checked, no shortage (at least 363 distinct articles per dev question). Not in the final setup (user, 2026-11-03); kept as a measured option, the clean GPU latency figure is dropped |
| Query rewriting | questions rewritten before the search | no | done on dev (`EXPERIMENT.md` 2026-11-02): replace -0.011 [-0.060, +0.040], fuse with the original +0.010 [-0.022, +0.045], neither an improvement by 3b. Fuse gains +0.075 [+0.010, +0.154] on the 15 ministry-sheet questions (exploratory, one of eight groups); hypothesis "helps everyday wording only" to be checked once on the test half. Off in the baseline |
| Heading style (D6) | none, label only, last 2, last 3 (baseline), full path, repeated levels merged, LLM-written sentence | yes, laptop | done: none -0.071 and label only -0.060 clearly worse; last 2, whole path, merged levels no difference; baseline last 3 stays. The LLM-written question (DeepSeek, added after the section titles, `header-llm`) gives nDCG@10 +0.035 [-0.025, +0.097], MRR@10 +0.088 [+0.000, +0.180], Recall@10 unchanged: not an improvement by 3b; the gain sits on model-written questions (same model family as the sentences), see `EXPERIMENT.md` 2026-11-03. It helps keyword search clearly (BM25 +0.129 [+0.054, +0.210], fusion +0.037 to +0.085 over the plain heading) but fusion does not beat dense on the same chunks. Not in the final setup (user, 2026-11-03) |
| Chunk limit | 1,024 against 512 tokens; overlap is not implemented | yes, laptop | done: 512 gives +0.002 [-0.031, +0.042], no difference; baseline 1,024 stays |
| Embedding model (D7) | bge-m3 against Qwen3-Embedding-0.6B (1,024 dimensions, Apache-2.0) | yes, laptop | done on dev: Qwen3-Embedding-0.6B nDCG@10 +0.033 [-0.036, +0.106], Recall@10 -0.024, not an improvement by 3b; bge-m3 stays |
| Annexes | searchable as they are, excluded, or summarised | excluded: no | closed without a run (user, 2026-10-31): annexes stay as they are; one dev question depends on an annex (`EXPERIMENT.md` 2026-10-31) |
| Language handling | filter on the question's language against no filter with merged translations; index scan with filter | no | done on dev for the filter: no filter -0.002 [-0.009, +0.003] nDCG@10, not an improvement; the filter stays. All dev questions are French, so English is untested; the index scan with filter is not tried |
| Article-number rule | queries naming an article go to keyword search; chosen instead: direct lookup by article number, named articles first | no | done on dev (`--article-lookup`, off by default): +0.016 [+0.000, +0.056] from one question (smoke-08, rank outside top 5 to rank 1), not an improvement by 3b; kept as a design choice for a known failure class (user, 2026-11-01). Off in the final setup (user, 2026-11-03); kept in the code (`--article-lookup`) and noted |

## Not decided yet

The choices inside each ablation above; the order after the reranker; whether to build the LLM-written heading.
