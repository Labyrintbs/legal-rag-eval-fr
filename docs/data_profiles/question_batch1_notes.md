# Question batch 1: 10 articles, 20 questions (step 0b)

Run on 2026-10-27. Articles drawn by `scripts/draw_articles.py` (seed 20261027; 5 Code du travail articles weighted by the ministry sheets that cite them, 2 random Code du travail, 3 random GDPR in chapters I-V and VIII-IX; three first draws replaced: D3332-8-2 needs the Commercial Code, GDPR articles 76 and 94 are institutional or final provisions). Written by `scripts/write_questions.py`: `deepseek-flash` writes one `plain.v2` and one `lay.v2` question per article, `deepseek-v4-pro` reviews (thinking off), automatic checks run first. The assistant then audited all 20 against the article text. Raw files are in `data/` (not committed).

## Cost

| Run | Calls | Estimated cost (ledger) |
|---|---|---|
| Writers (20 calls, flash) | 20 | 0.0020 USD |
| Reviews (20 calls, pro) | 20 | 0.0097 USD |
| Batch total | 40 | 0.0118 USD |
| All calls so far (pilot + batch) | 84 | 0.0320 USD |

The balance lags one run behind (the account page says up to 5 minutes, and in practice longer). Over the two runs that had settled, the balance fell by 0.07 and 0.06 CNY for estimates of 0.0109 and 0.0093 USD, about 6.5 CNY per estimated USD, so the ledger estimate is in the right range. The balance dropped 0.13 CNY in total (46.67 to 46.54) against 0.0320 USD estimated for 84 calls, with the last batch not yet reflected. To confirm once it settles.

## Result

| | Count |
|---|---|
| Reviewer accepted, no check flag | 17 |
| Doubtful (flagged by the overlap check, reviewer accepted) | 3 |
| Audit: accept | 13 |
| Audit: reject or rewrite | 7 |

The reviewer accepted every one of the 20 questions, including the 7 the audit rejects: a miss rate of 7 of 20 on this batch (n is small, so the interval is wide). The audit is one reader's judgement, not ground truth.

## What the audit found

1. **Missing scope (4 questions, 2 more partly).** The writer sees the article body only. For articles whose meaning depends on their section, the question loses its scope: L6325-10 (contrat de professionnalisation), R4227-55 (fire and explosion chapter), R7422-11 (home workers). Asked without the scope, the question is ambiguous and other articles may answer it, so the gold would be wrong. The reviewer, which sees the same body only, cannot catch it.
2. **Question contains its own answer or mixes concepts** (R7422-11 lay), **an answer slightly off** (L2232-25 lay: majority of members instead of majority of votes), **a vague question** (L2315-38 lay: "le comité").
3. **The overlap check has false positives.** 3 questions were flagged, 2 of them fine (L1233-24-1 lay, GDPR 82 lay): words such as accord, licenciements, salariés are unavoidable. A threshold of 0.5 on raw word overlap is too strict for these articles.
## Rerun on the same 10 articles with v3 prompts

`plain.v3` and `lay.v3` give the writer the last four section levels as context ("Contexte") and ask it to name the situation the article applies to, not to contain its own answer, and not to use vague words. `reviewer.v2` sees the context and checks that the question names its scope. Thinking stays off. Cost: 0.0125 USD estimated (all calls so far 0.0445 USD for 124 calls).

| | v2 | v3 |
|---|---|---|
| Audit: reject or rewrite | 7 of 20 | 6 of 20 |
| Missing-scope errors | 4 (L6325-10 and R4227-55, both styles), 2 partly | 0 (all four now name the contract or the fire risk) |
| Errors the pipeline did not flag | 6 of 20 | 3 of 20 |
| Doubtful list that were real errors | 1 of 3 | 3 of 7 |

Errors that remain in v3, none of them a missing scope:
- A compound question the check missed (L1225-56 plain: "...et est-il payé ?"). The check now also catches "et est-il", "et est-elle" and similar; replayed offline on the stored questions it flags this one and the GDPR 15 lay one.
- A self-answering question that persists (R7422-11 lay) and a vocabulary mix-up that persists (L2232-25 lay: "désigné" against "mandaté"). The reviewer accepted both again.
- One reviewer false reject (R4227-55 plain: the short answer omits a condition, the question asks who) and a correct reject (GDPR 82 lay: the article only points to article 79).

These prompts were tuned on these 10 articles, so the v3 numbers are optimistic. The next check must use new articles.

## Choosing the reviewer, and the corrected audit

The thinking-off reviewers (v3 checklist, v4 evidence first) caught 4 and 5 of the audited errors. The thinking-on reviewer at effort `low` flagged questions the first audit had accepted; reading its reasons, three were real errors and five fair but strict points, so the audit was corrected (`scripts/reviewer_eval.py`: 16 errors, 5 borderline left out, 19 fine). On the corrected labels, over the 40 questions of the two batches (temperature 0 where it applies):

| Reviewer | Errors caught (of 16) | Fine questions flagged (of 19) |
|---|---|---|
| v3, thinking off | 4 | 0 |
| v4, thinking off | 5 | 0 |
| v3 and v4 together, thinking off | 7 | 0 |
| v4, thinking on, effort low | 15 | 3 (two were reviews cut at the 4,000-token limit, now 8,000) |

Per the DeepSeek docs, `reasoning_effort` only sets the depth of thinking (`none` disables it); with thinking disabled the setting changed nothing in a test (identical 236 output tokens). A thinking-on review costs about 0.005 USD and 23 seconds (2,500 reasoning tokens), against about 0.0005 USD and a few seconds. Reviews now run 8 at a time under one shared budget that counts calls in flight.

## Fresh batch (batch 2): the final pipeline on new articles

10 articles drawn with seed 20261028, excluding every earlier article, no manual rejection. Writer v3, automatic checks, reviewer v4 with thinking on at effort low. Cost 0.1204 USD estimated for 20 writes and 20 reviews. The prompts were not changed after seeing this batch.

| | Count |
|---|---|
| Accepted by the pipeline / on the doubtful list | 13 / 7 |
| Audit: real errors | 5, all on the doubtful list |
| Audit: borderline (minor) | 5 (2 on the doubtful list, 3 accepted) |
| Audit: clean | 10 |
| Real errors accepted silently | 0 |
| Missing-scope errors | 0 |

The 5 real errors: a short answer that lists one document where the question asks for all of them (R1263-1), a missing "du comité social et économique" (L2315-81-1 plain), a question that asks "quand" where the article sets no deadline (L2315-81-1 lay), and an unconditional "Oui" where the GDPR article 27 has conditions and exceptions (both styles). The auditor saw the reviewer's reasons, so the audit may be anchored by them: a spot check by the user of the 13 accepted questions is the way to confirm.

**Style differences (both runs).** Technical articles on staff representation and collective agreements (L1233-24-1, L2315-38, L2232-25) make awkward lay questions. The GDPR and the plain-rule articles (L1225-56, GDPR 15) give good ones.
