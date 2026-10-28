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

## The model-written set: batches 2, 3 and 1c

All 50 questions come from the final pipeline (writer `plain.v3`/`lay.v3`, automatic checks, reviewer v4 with thinking on at effort low), on 25 articles: batch 2 (10 fresh articles), batch 3 (5 fresh articles: 2 weighted and 1 random Code du travail, 2 GDPR) and batch 1c (the batch 1 articles written again). The assistant audited every question with the reviewer's reasons in view. Consolidated, with the audit reason of each, in `data/questions/model_written.json` (not committed).

| | Count |
|---|---|
| Questions | 50 |
| Real errors (dropped) | 15 |
| Borderline (kept, noted) | 7 |
| Clean | 28 |
| Kept | 35 (24 Code du travail, 11 GDPR; 19 plain, 16 lay) |

The pipeline put 17 questions on the doubtful list, 12 of them real errors; it let 3 real errors through: R7343-43 plain (the vote concerns the platform workers' organisations; the writer left that out although the context named it), GDPR 8 lay ("16 ans" without the national-law lower limit down to 13) and L2232-25 lay ("désigné" for "mandaté", which the same reviewer had flagged in an earlier run: thinking mode has no temperature control, so its verdicts vary between runs). Recall on real errors was 5 of 5, 3 of 5 and 4 of 5 in the three batches, 12 of 15 together. Five articles keep no question (L1225-56, L2315-81-1, R7343-43, GDPR 27 and 34). Cost of batches 3 and 1c: 0.1482 USD estimated; the whole project so far 0.6118 USD estimated for 427 calls, and the balance fell from 46.67 to 43.19 CNY, about 5.7 CNY per estimated USD.

## Replacement batches with the conditions style (batches 4b and 5)

New style `conditions.v1` (a person describes a case with one detail, the question is about one condition, threshold, deadline or exception; 35 words at most) and `reviewer.v5` (reviewer.v4 plus the conditions style). Batch 4b: 11 new articles (seed 20261029, earlier articles excluded; 3 institutional draws replaced: L1442-13-3, R8124-2, GDPR 31), `plain.v3`, `lay.v3` and `conditions.v1` each: 33 questions, 0.1981 USD estimated. Batch 5: the 5 articles with no kept question (L1225-56, L2315-81-1, R7343-43, GDPR 27 and 34), `conditions.v1` only: 5 questions, 0.0340 USD. The assistant audited all 38 against the article text, with the reviewer's reasons in view.

| | Count |
|---|---|
| Questions | 38 |
| Real errors / borderline / clean | 12 / 6 / 20 |
| Flagged by the pipeline | 14 (9 real errors, 5 false alarms) |
| Real errors accepted silently | 3 (R2152-13 plain, L2315-81-1 conditions, R7343-43 conditions) |
| Kept | 26 |

Errors by style: plain 2 of 11, lay 2 of 11, conditions 8 of 16 (4 of 11 on the new articles, 4 of 5 on the articles that already failed twice). The conditions style invents or bends a premise more often (an employer that is a public authority; a deadline where the article says "au besoin"; a vague "les activités visées"). Silent errors over the four batches: 15 of 27 real errors were flagged in the first three, 9 of 12 here; the two repeat articles L2315-81-1 and R7343-43 fail again because the question asks for something the article does not fix. With all batches, the model-written set is 88 questions, 61 kept. The conditions questions are kept in a separate group H so their weaker reliability shows in the group tables.

## Source 4: questions from the ministry sheets (2026-10-28)

Candidates: section headings in the form of a question, with 1 to 4 cited Code du travail articles all present in our corpus, none already used as a gold article: 205 headings in 102 sheets (`data/external/fiches-travail.json`, sha256 in `data/drawn/batch1.json`). One heading per sheet in random order (seed 20261030), the assistant read every cited article in the database against the heading, then 46 more single-citation headings.

| Result | Count |
|---|---|
| Headings audited | 78 + 46 single-citation |
| Citations that answer the heading | 12 |
| Heading kept, right article found by the assistant | 17 |
| Dropped (wrong citation and no clear answer article, vague heading, or an answer spread over many articles) | the rest |

Typical citation faults: the cited article is a neighbour or a related penalty (rupture conventionnelle content cites the dismissal indemnity L1234-9; number of delegates cites the central delegate L2143-5; public holidays cite the Alsace-Moselle list), or the sheet cites the exception and not the rule. This is why the ministry gold cannot be used as given. Questions use the heading, shortened or completed with the sheet topic to stand alone. 29 questions result, in group I; 4 gold lists are marked needs_review (CDD d'usage, jours fériés, congé de présence parentale, délai de carence en intérim).

## Source 5 and the DeepSeek second opinion on the gold (2026-10-28)

**Hand-written questions (13, group G except two).** Cross-source or single-source answerable (hw-01 to hw-04), false premise (hw-05 to hw-08: a fixed three-month notice, a two-year seniority for the dismissal indemnity, a GDPR ban on all transfers, a compulsory trial period), unanswerable (hw-09 to hw-11: German minimum wage, Belgian parental leave, limitation of tax fraud), underspecified (hw-12 "Quel est le préavis ?", hw-13 leave for a death in the family). Cross-source questions are rare: the GDPR articles are general, so only hw-01 (surveillance: L1222-4, L2312-38, GDPR art 13) and smoke-25 are really both-source; hw-04 had a GDPR article (art 5) as acceptable, which the judge graded 0 and was dropped.

**The judge.** `judge.v1` then `judge.v2` (adds: an article that corrects a false premise answers the question). Input per question: the gold articles and the first 8 distinct articles of the dense search in the question's language, in random order, texts cut at 3,000 characters, no hint of the gold. Output: a grade 0, 1 or 2 per article with the words that justify it, and a verdict on the question (answerable, false_premise, underspecified, unanswerable, sure or not). Cost: 0.1292 USD (v1, 1,200 characters), 0.132 USD (v1, 3,000), then about 0.13 and 0.17 USD for the two v2 runs; all calls so far 1.41 USD estimated for 598 calls.

Two flaws of mine before the result could be read: the first run cut articles at 1,200 characters, so the judge graded GDPR art 12 (the one-month deadline in paragraph 3) and art 15 as 0; and `judge.v1` graded the correcting article of a false-premise question 0. Both fixed (3,000 characters, `judge.v2`). The thinking mode varies from run to run, so only changes seen in several runs or confirmed by reading the article were adopted.

| Over 51 questions | Result |
|---|---|
| Fully agree with the gold (judge.v2) | 12 of 29 sheet, 8 of 22 hand-written and smoke |
| Real gaps found in the gold | L4121-3-1 (states what the DUERP is for; the ministry cited R4121-1), R2312-8 (BDESE content under 300 employees), the regulatory articles of the congé de présence parentale, L3122-20 (default night work hours), R4624-42 (conditions of the inaptitude finding), recital 59 (one-month deadline), L1221-20 (purpose of the trial period) |
| Gold lowered or dropped | art 5 (hw-04), art 88 and recital 155 (smoke-25), L1232-1 (smoke-13), L2143-12 (sheet-18), L1237-1 only acceptable (hw-12) |
| Raised to equal | smoke-21 (art 44, 45, 46, 49 all primary: stable in three runs), recital 23 (smoke-22), D1242-1 (sheet-14) |
| Kind disagreements | smoke-27 and hw-13 (underspecified): the judge calls them answerable because the corpus covers every case; canicule (sheet-05): the judge calls it unanswerable, not sure |

The judge confirmed the audit's overall shape and found about ten articles the audit had missed, in both directions. Where it and the assistant still differ the list stays needs_review: hw-01, hw-13, smoke-15, smoke-25, smoke-27, sheet-05.

**Third opinion (flash, thinking on, judge.v2).** For the 6 lists still needs_review, `deepseek-flash` judged the same candidates (0.0104 USD estimated). Rule fixed before the run: a list passes if the kind agrees, every primary gold article gets at least 1, and the judge gives no 2 to an article outside the gold; a failing question would be dropped. All 6 pass, none dropped. smoke-27 loses L3142-1 (graded 0 in all four runs) and flash agrees it is underspecified; hw-01, hw-13, smoke-15, smoke-25 and sheet-05 become checked. No list is needs_review any more; the user's spot check remains.

## Second reviewer on the model-written questions (2026-10-28)

The 61 kept model-written questions went through the same blind pooled judge as the others (`judge.v2`, `deepseek-v4-pro`, thinking low, the source article plus the top 8 dense-search articles in random order; 0.355 USD, and 0.0065 USD for one rerun after a failed reply). Gold files are in `data/gold/judge_mw.json` and `judge_mw64.json`.

| | Count |
|---|---|
| Questions judged | 61 (60 on the first run, mw-064 on a rerun) |
| Source article confirmed as grade 2 | 60 of 60 on the first run |
| Questions where the judge adds nothing | 30 |
| Other articles graded 2 by the judge | 20 question-article pairs (16 distinct articles) |
| Questions dropped | 2 |
| Kind disagreement | 1 (mw-061, underspecified) |

What the extra articles are, after reading each: 12 recitals of the GDPR that restate the article (added as acceptable, grade 1), the Code du travail articles that give the same rule for another case or state it again (acceptable), and 3 that answer as well as the source (grade 2): L4624-1 for mw-001, R4623-14 for mw-002 (the nurse refers the worker to the doctor), R1233-31 for mw-023 (the 4 to 12 months of the congé de reclassement, which is the real answer to "durée maximale"), and art 42 for mw-074 (a certification does not reduce responsibility).

The two dropped questions are errors the first reviewer and the assistant's audit both missed: mw-061 (lay) answers "neuf semaines" for a unilateral spread of working hours, but L3121-45 sets 9 weeks under 50 employees and 4 weeks from 50; mw-064 ("les règles ... près des lignes électriques du train") fits three chapters that all exclude rail traction, so the gold would punish the other two. The model-written set is now 59 kept questions; gold file: 130 questions, 183 gold articles, none needs_review.
