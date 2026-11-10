# Step 0d summary: answers with citations, refusals and guardrails

Written 2026-11-10 for the review gate. Decisions are in `docs/decisions/0006-step-0d-decisions.md` (1 to 19); every run is logged in `EXPERIMENT.md`.

## What was built
- **Cited answers.** The question goes to our search (top 5 articles), each article is cut into numbered legal units (a sentence or a list item), and the model must reply in a fixed format: a refusal flag, or claims that each name the units that support them. Our code drops any citation that does not exist and any claim without one, and shows the reader the exact cited passage.
- **LlamaIndex as the frame** (retriever, node post-processor, query engine, DeepSeek connector). The checks stay in plain code.
- **Refusals in three layers:** weak search (top-1 similarity under 0.55, no model call), the model's own refusal, and the code check.
- **Tracing:** one row per request in Postgres (`query_traces`, 30-day expiry), JSON logs without the question text, and commands to list failures, summarise, export candidates for the eval set and purge.
- **Limits and a kill switch:** per client 5 questions a minute and 30 a day, $0.10 a day for the whole service, and a flag in the database (`legalrag service llm-off`) that stops the model while search keeps working. Search is never limited. The visitor still gets the 5 articles and a reason (HTTP 429 or 503).
- **A claim judge** (is a claim backed by the passage it cites?) validated on 49 claims you labelled, and the answer metrics built on it.

## Choices made
Model `deepseek-flash` with thinking off (same results as `deepseek-v4-pro` at a quarter of the cost), prompt `answer.v3`, refusal threshold 0.55, judge `deepseek-flash` with `judge.v2`. We kept our own answer path and did not adopt LlamaIndex's `CitationQueryEngine`.

## Results on the 65 French dev questions
| | |
|---|---|
| Answerable questions answered | 55 of 58 (the 3 refusals are search misses: the right article was not in the top 5) |
| Unanswerable or false-premise questions refused | 5 of 6 (the sixth corrects the false premise) |
| Answers citing a gold article | 51 of 55 |
| Claims the judge calls supported / partly / not supported | 85% / 13% / 2.4% (the judge flags about a quarter of good claims, so read 85% as a lower bound) |
| Cost and speed | about $0.0004 per question, median 1.65 s |

**The judge**, checked against your labels: agreement 82%, kappa 0.68, it caught all 17 real errors and flagged 8 of 32 good claims.

**Against LlamaIndex's `CitationQueryEngine`** (same search, model and judge): the same faithfulness and gold citations. Ours shows the exact passage (311 characters against 920) and gives a clear refusal signal; the engine does not. The engine is simpler.

## Final numbers on the test half (opened once, settings frozen)
63 French test questions, same settings as dev.

| | Dev (65) | Test (63) |
|---|---|---|
| Answerable questions answered | 55 of 58 | 50 of 57 (the 7 refusals are all search misses) |
| Answers citing a gold article | 51 of 55 | 47 of 50 |
| Supported / partly / not supported claims | 85% / 13% / 2.4% | 86% / 12% / 2.1% |
| False-premise questions | 1 of 2 answered, correcting the premise | 3 of 3 answered, correcting the premise (read) |
| Unanswerable questions refused | 3 of 4 | 1 of 1 (stopped by the weak-retrieval check at 0.54, just under the threshold) |
| Cost and speed | about $0.0004 per question, median 1.65 s | about $0.0004 per question, median 1.61 s |

Faithfulness and citations hold on the test half. The extra search misses (7 against 3) are why fewer answerable questions are answered.

## English check on an outside dataset (ClaimRAG-LAW, GDPR)
66 expert-reviewed questions, but they cover only 4 articles (38 are on article 49). With the dataset's own source text as the only source: 93% supported claims. With our full search: 87% supported, and the right article in the top 5 for 70% of the questions (articles 1, 8 and 28 almost always, article 49 for half, and several of those misses ask about the information duties of articles 13 and 14, so the dataset's label is doubtful). Completeness against the expert reference claims is about 70% in both setups, but this is **indicative only**: your hand check agreed with the judge claim by claim only at kappa 0.01, though the total came out the same.

## Known limits
- Completeness is not measured on French, and the English figure is rough.
- The judge is the same model as the answerer, and flags more than it should.
- The English set is narrow (4 articles); the French results come from 65 dev questions.
- The test half has not been opened for answers.
- The service does not exist yet: the limits are tested but not wired to a web layer, and two requests at the same instant can slip past a limit.
- The article-number rule (for questions such as "Que dit l'article L1221-13 ?") is not active, and `smoke-08` shows that it would help.
- Tables in the Code du travail are flattened into text (for example R2314-1, the CSE delegation table), which hurts search for those articles.
- The index recall issue is explained (a setting): the service must set `hnsw.ef_search` to at least 100 or use the exact scan.

## Cost
The DeepSeek ledger holds $3.33 in total for the project.

## For the review gate
1. Approve step 0d.
2. Open the test half once for the final answer numbers, with everything above frozen (the same rule as in 0c)? About 5 cents.
3. Next is 0e (the quality gate in CI), then 0f (web service and demo page, where the feedback box and the article-number rule can be decided).
