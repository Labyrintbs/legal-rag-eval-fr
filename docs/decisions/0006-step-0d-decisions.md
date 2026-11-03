# Decisions of step 0d (answers and guardrails)

Started 2026-11-03, after the review gate of 0c (`0004`). One decision at a time, with options; this file lists what is decided and what is not.

| # | Decision | Who, when |
|---|---|---|
| 1 | An answer cites the article **and the exact passage** (not the article alone) | User, 2026-11-03 |
| 2 | Granularity G1: the retrieved chunk is the source shown to the model; inside it the text is split into numbered **legal units** (sentence, list item, GDPR paragraph or point). The model answers with the ids of the units it used; the passage shown to the reader is the stored text of those units, never text written by the model. A list item is shown with its lead-in. Rejected: chunk-only citation (not the exact passage), fixed windows inside the chunk | User, 2026-11-03 |
| 3 | No provider citation feature (Anthropic Citations API): it ties the project to one provider and a higher price; the LLM stays behind one adapter | User, 2026-11-03 |
| 4 | L2: LlamaIndex as the orchestration layer around our own retrieval (a retriever that calls our exact search, a node post-processor that numbers the units, a query engine with `structured_predict` and the DeepSeek connector). The id resolution, the refusal rule and the tracing stay in plain code, tested without the framework. Rejected: the full LlamaIndex stack (not the retrieval we measured), our code only with LlamaIndex later | User, 2026-11-03 |
| 5 | In the answer metrics, our design is compared with LlamaIndex's own `CitationQueryEngine` (same retrieval, same model, same dev questions): answer support, citation precision, passage length, refusals, cost and speed. If the default is as good and simpler, we consider using it | User, 2026-11-03 |
| 6 | Legal-unit rule (`src/legalrag/units.py`): a unit is a slice of the chunk text (sentence; numbered list item 1°, 2°… incl. "bis"; GDPR point a), b)); a numbered list counts only if it opens a line or follows a colon, so "aux 1° et 2° de l'article…" is not a list; a GDPR paragraph number ("1.") stays with its sentence; an item or point is shown with its lead-in, with " […] " where units are skipped | Assistant, to confirm, 2026-11-03 |

Measured on the 12,136 default chunks (2026-11-03): no violation of the slice rules (every unit is a slice, in order, only whitespace between units); median 2 units per chunk, 99% at most 16, largest 81; unit length median 165 characters, 90% at most 364, largest 3,745; 2,282 lists or point groups, 2,280 introduced by a colon (the 2 others are GDPR definitions). The old sentence splitter treated 43% of the numbered lists as one sentence. The abbreviation "art." followed by a capital or a digit does not occur in the corpus, so the known limit of the sentence splitter on "l'art." has no effect.

Facts behind the decisions (measured 2026-11-03): the median chunk has 2 sentences and 229 tokens, the largest 42 sentences; 22% of the 11,425 Code du travail articles contain a numbered list (1°, 2°…), and 43% of those (1,068) are a single sentence for the old splitter; 82 of 99 French GDPR articles have numbered paragraphs and 44 have (a), (b) points. `llama-index-core` 0.14.25 with `llama-index-llms-deepseek` 0.4.1: 69 packages, 148 MB, 5.5 s import, 141 MB of memory; the connector accepts `deepseek-flash` and `structured_predict` returned a validated answer (it works through prompt parsing, the connector reports no function calling).

## Not decided yet
How many articles go into the prompt; which model writes the answers; the refusal rule and its threshold; the answer prompt; the tracing table layout; rate limits; how the judge is validated (30 to 50 labelled answers) and whether the test half is opened for the final answer numbers.
