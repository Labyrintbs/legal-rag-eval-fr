# Decisions of step 0b (evaluation set and metrics)

Draft started 2026-10-27, one decision at a time with the user. Rows are added as they are decided; undecided points are listed at the end.

## Decided

| # | Decision | Who, when |
|---|---|---|
| 1 | Baseline rule: the search keeps only chunks in the question's language; gold is per language. Evaluation uses exact search on the filtered rows, recorded in each run's settings. Ablations in 0c: index with iterative scan, and no filter with translations merged into one article | User, 2026-10-27 |
| 2 | Two grades: primary (2) states the answer; acceptable (1) also answers it alone or mostly, including the Code du travail articles with an identical body. Background that only helps a reader is not gold. Uncertain grades are flagged in a `review` field | User, 2026-10-27 |
| 3 | Reported for every run: Hit@5; Recall@5, @10, @20; MRR@10 (primary article); nDCG@5, @10 (grades 2 and 1). Headline: nDCG@10, revisited in 0d once the number of chunks given to the answer step is fixed. Rank counts articles (chunks merged). Unanswerable questions are left out of these averages. Every number has a bootstrap interval and a per-question-type split | User, 2026-10-27 |
| 3b | Guardrail for comparing runs in 0c: a change is an improvement only if nDCG@10 rises and Recall@10 does not fall by more than its bootstrap interval | User, 2026-10-27 |
| 4 | Metric code is our own, with hand-computed tests, cross-checked once against `ir_measures` (same nDCG gain variant in both). If any metric looks odd or distorted, recompute it with the standard library before trusting it | User, 2026-10-27 |
| 5 | Dev/test split by primary article, about 50/50, balanced within each question group (and source). Fixed rule: inside each group, articles are ordered by a hash of the article id and alternate between dev and test. All questions with the same primary article stay in one half. 0c tunes on dev only; test is computed once at the end of 0c and again in 0d and 0e, never to choose a variant | User, 2026-10-27 |
| 6 | Judge validation (30 to 50 hand-labelled answers) moves to 0d, where answers first exist. 0b instead checks the quality of model-written questions: the user reviews a random sample (about 20 of 50) and the acceptance count is recorded before the rest are written | User, 2026-10-27 |
| 7 | Model-written questions use the DeepSeek API (the user's account), not Claude. A 3-article pilot runs on both `deepseek-flash` and `deepseek-v4-pro`, thinking off, and the model is chosen after comparing. Caps: 1 USD per run, 5 USD in total, enforced by `llm.py` before each call (worst case: peak price, every input token a miss, full `max_tokens`). Each call is logged in `data/llm_ledger.jsonl` and checked against the account balance (CNY) before and after each run. The key is in `.env` (gitignored). Only article text of public law is sent | User, 2026-10-27 |
| 8 | About 110 independent questions to start (form variants and group G not counted in n). Group tables are diagnostic, with intervals, never the headline; decisions use the overall nDCG@10 and the guardrail. The bootstrap resamples articles, not single questions; at most 3 to 4 questions per article. Later, after 0c shows which comparisons are too close to call, batches are added in that group (up to about 200) | User, 2026-10-27 |
| 9 | From the growth batches on, a model reviews generated questions and reports only the doubtful ones; the user and the assistant review those together. A random audit sample of the accepted ones is also checked, to measure what the reviewer misses. The reviewer is a different model from the writer | User, 2026-10-27 (audit and rule added by the assistant, to confirm) |

| 10 | Flash writes with `plain.v2` and `lay.v2` (one idea per question, 30 words at most, counter-example in the prompt); pro reviews with thinking off, to be revisited after the full set. Automatic checks (JSON keys, article number, wording overlap, compound question, length, duplicates) run first on every question and put it on the doubtful list. The pilot is in `docs/data_profiles/question_pilot_notes.md` | User, 2026-10-27 |

| 11 | The writer sees the last four section levels as context (`plain.v3`, `lay.v3`). The reviewer is `reviewer.v4` (evidence first, then a checklist; the code decides that any failed check puts a question on the doubtful list) on `deepseek-v4-pro` with thinking on at effort `low`, 8,000 max tokens, run 8 at a time. Thinking-off reviewers caught 7 of 16 audited errors at best. Flags loosened: overlap 0.8 for lay, 35 words. `reasoning_effort` is part of thinking mode in the DeepSeek API, so "more effort with thinking off" does not exist. The assistant triages the doubtful list and reports only the important cases to the user | User, 2026-10-27 |
| 12 | The first audit was corrected (3 real errors, 5 borderline). The fresh batch (10 articles, final pipeline, no prompt change after seeing it) had 5 real errors, all flagged, 0 accepted silently, 0 scope errors. The assistant sees the reviewer's reasons while auditing, so the user spot-checks accepted questions | User, 2026-10-27 |

| 13 | 50 model-written questions from 25 articles (batches 2, 3 and 1c): 15 dropped by the audit, 35 kept, 7 of them borderline. The pipeline flagged 12 of the 15 real errors; the audit found the 3 it missed. Next: the other sources (ministry sheets, hand-written, unanswerable) | User, 2026-10-27 |

## Not decided yet

How the articles for the 20-question batch are chosen; gold file fields; sources and mix of the question set.
