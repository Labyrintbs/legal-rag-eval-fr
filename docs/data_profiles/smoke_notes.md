# Smoke retrieval notes (Loop 4)

Run on 2026-10-27: `make smoke`, 29 questions from `tests/smoke_questions.yaml`, BAAI/bge-m3 on the Mac CPU (torch 2.11), run `default` (12,136 chunks), nearest 5 chunks by cosine distance, no filter, no keyword search, no reranker. Full output: `smoke_output.txt` (a snapshot of that run). This is an inspection, not a metric: 29 questions, one model, expected articles chosen by hand.

## Result

Expected article in the top 5 for 21 of the 27 questions that have one (Q28 and Q29 have none).

| Group | Questions | In top 5 | Misses |
|---|---|---|---|
| A plain lookup | 4 | 4 | |
| B wording gap and form | 5 | 3 | Q6, Q8 |
| C split articles and annexes | 3 | 2 | Q11 |
| D several articles or explanation | 3 | 2 | Q13 |
| E GDPR in French | 7 | 6 | Q22 |
| F language and sources | 3 | 2 | Q25 |
| G no plain answer | 4 | 2 of 2 with an expected article | |

Rank of the first expected article when found: rank 1 for 14 questions, rank 2 for Q4, Q9, Q10, Q20, Q21, rank 3 for Q3, rank 4 for Q16.

## The six misses (what the results show)

- **Q6** "Peut-on mettre fin à un CDI d'un commun accord ?" (expected L1237-11, the rupture conventionnelle): the top 5 are L1237-17, L1237-19-2, -14, -10 and D1237-8, so the right chapter but not the article. The question does not use the legal term.
- **Q8** "Que dit l'article L1221-13 ?": the exact article is not in the top 5; neighbours with similar numbers are (R1221-34, L1221-12, D1221-23). The number in the chunk header did not make the embedding match the number in the question. An exact lookup is not what vector search does well.
- **Q11** prud'hommes de Lyon: the top 5 are articles about the conseil de prud'hommes (L1422-1, R1422-2 and so on), not the annex table that lists the districts. Lyon is in chunk 2 of that annex (flattened table).
- **Q13** étapes d'un licenciement pour motif personnel: ranks 1 and 2 are L1233-15 and L1233-7, which belong to chapter L1233 (licenciement économique); L1232-1 is at rank 4. None of L1232-2, -3, -6 is in the top 5. My expected list may also be incomplete (L1232-1 is the general article).
- **Q22** GDPR applying to a company outside the EU: the top 5 are recitals 13, 101, 115, 25 and art. 47 chunk 3; none is art. 3 or recitals 22, 23.
- **Q25** surveillance of e-mails: no result is about monitoring or data; the top 5 are R/D articles (D4163-32, R4722-12, D4163-4, R4722-13, R4446-3; not read). Neither source's expected article came back (L1222-4, L1121-1, art. 88, art. 6).

## Other observations

- **Close calls.** In group A the first expected article is at rank 3 for Q3 (D3142-82 at 0.335, L3121-66 at 0.358, L3141-3 at 0.359) and rank 2 for Q4 (L1242-10 first). The top-5 distances lie in a narrow band (about 0.32 to 0.37), so small differences decide the order. Q16: art. 7 ("conditions applicables au consentement") is first and art. 4 chunk 2/3, which holds the definition, is fourth; art. 7 is arguably a good answer too.
- **Both languages in one list.** For French questions, 8 English chunks appear in the top 5 lists (for example art. 17 [en] at rank 5 for Q15 and rank 3 for Q17; art. 33 [en] at rank 3 for Q19). They duplicate the French result and use up places. The English questions (Q23) return English chunks only. Q24, an English question over French law, found L3121-27 at rank 1.
- **Corpus mix.** Q20 (administrative fines) has other Code du travail articles at ranks 1, 3, 4 and 5 (L8115-3, L8291-2, L1264-3, R7122-26; not read) and art. 83 at rank 2; the question does not say "RGPD".
- **Long annexes crowd the list.** For Q12, 4 of the top 5 chunks are different chunks of the same annex (chunk 1, 7, 11 and 12 of 31).
- **Split articles.** Q10: R2312-9 is found at rank 2 through its first chunk (chunk 1 of 15).
- **Distance and no answer.** The best distance for the questions with a found article is 0.232 to 0.383 (largest: Q4, 0.383). The six misses have 0.337, 0.340, 0.356, 0.414, 0.415, 0.425 and the two questions without an answer 0.445 (Q29) and 0.459 (Q28). So top-1 distances above 0.40 are all misses or unanswerable here, but that is 5 questions; this is a hint for the refusal rule in 0d, not a threshold.
- **False premise and underspecified.** Q26 (39 hours) returns L3121-27 at rank 1 and Q27 (days of leave) returns L3141-3 at rank 1; correcting the premise or asking for details is a job for the answer step (0d).
- **Questions without an answer.** Q28 (SMIC amount) returns D3231-6 and D5122-13, D5522-16, R5122-18, D5424-74 (not read); Q29 (theft penalty) returns L8234-1, L1255-14 and others. Nothing signals that the corpus has no answer except the distance.

## What to look at in 0b and 0c

- Exact article references (Q8): keyword search or a direct lookup by number.
- Questions in everyday words (Q6, Q25, Q22): query rewriting, a reranker, or both.
- Annex tables (Q11) and long annexes (Q12): the annex handling and the chunk size experiments; per-article grouping of results.
- French and English chunks together: a language filter, or one unit for both (note the index limit with filters, see `EXPERIMENT.md` 2026-10-26).
- Close calls in the narrow distance band (Q3, Q4, Q16, Q20): reranker.
- Check the expected lists of Q13 and Q25 before using them as an evaluation set.
