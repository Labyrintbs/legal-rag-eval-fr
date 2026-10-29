# Decisions of step 0c (retrieval experiments)

Started 2026-10-29. Every run is compared with the dense baseline on the dev half using the paired difference and the guardrail of decision 3b in `0003-step-0b-decisions.md`. The test half is opened once, at the end of the stage.

| # | Decision | Who, when |
|---|---|---|
| 1 | Experiment A (keyword search): BM25 on the lexemes Postgres stores in `chunks.tsv`, alone and fused with dense by reciprocal rank fusion (k 60, top 100 articles each, optional weight on the keyword list). No setting is an improvement on dev (`EXPERIMENT.md` 2026-10-29), so dense stays the retrieval default | Assistant result, to confirm |
| 2 | Chunking variants (header none, label, full path, collapsed repeats; 512-token limit) are embedded on the Windows laptop and shared as the Release `embeddings-bge-m3-variants-v1` (`docs/handoff/variants_windows.md`). Overlap between chunks is not implemented and is not tried | User, 2026-10-29 |

## Not decided yet

Whether to try a rule that sends queries naming an article number to keyword search; reranker; language handling (iterative scan with filter, no filter with merged translations); annexes as they are, excluded or summarised.
