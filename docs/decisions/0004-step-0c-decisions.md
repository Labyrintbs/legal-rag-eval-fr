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
| Keyword search and rank fusion | BM25 over Postgres lexemes alone and fused with dense (weights 1, 0.5, 0.25); Postgres `ts_rank` and bge-m3 sparse are untried | no | done for BM25, no improvement |
| Reranker | bge-reranker-v2-m3 against Qwen3-Reranker-0.6B against none, with CPU latency per question (P5); Jina excluded (CC-BY-NC) | no | bge-reranker-v2-m3 running; latency not recorded yet |
| Query rewriting | questions rewritten before the search | no | not started |
| Heading style (D6) | none, label only, last 2, last 3 (baseline), full path, repeated levels merged, LLM-written sentence | yes, laptop | six variants ready for the laptop; the LLM-written sentence is not built (about 12,000 DeepSeek calls, ask first) |
| Chunk limit | 1,024 against 512 tokens; overlap is not implemented | yes, laptop | `size-512` ready for the laptop |
| Embedding model (D7) | bge-m3 against Qwen3-Embedding-0.6B (1,024 dimensions, Apache-2.0) | yes, laptop | not started; needs a handoff and a model-aware search |
| Annexes | searchable as they are, excluded, or summarised | excluded: no | not started |
| Language handling | filter on the question's language against no filter with merged translations; index scan with filter | no | not started |
| Article-number rule | queries naming an article go to keyword search | no | not started; the dev set has one such question |

## Not decided yet

The choices inside each ablation above; the order after the reranker; whether to build the LLM-written heading.
