# Smoke retrieval notes (Loop 4)

Run on 2026-10-27 with `make smoke`: 29 questions from `tests/smoke_questions.yaml`, BAAI/bge-m3 on the Mac CPU (torch 2.11), run `default` (12,136 chunks), nearest 5 chunks by cosine distance, no filter, no keyword search, no reranker, `hnsw.ef_search` 100. Full output: `smoke_output.txt` (a snapshot of that run). This is an inspection, not a metric: 29 questions, one model, expected articles chosen by hand.

I read the full text of every retrieved chunk and of every expected article that did not come back. The verdicts below are my reading of those texts, not only of the article numbers. Where a claim comes from a separate check, the check is named.

## Two corrections to the first version of these notes

1. **Q25 was not a miss.** With the index setting first used (`ef_search` 40, pgvector's default), the index returned a top 5 that differed from the exact top 5 for Q25: article 88 (distance 0.423, closer than the 5th result at 0.430) was missing. With `ef_search` 100 the index gives the exact result for all 29 questions. Q25 now finds GDPR article 88 at ranks 4 (French) and 5 (English). Details in `EXPERIMENT.md`, 2026-10-27.
2. **Some explanations were too quick.** Q6, Q10 and Q20 are described again below after reading the texts.

## Result

Expected article in the top 5 for 22 of the 27 questions that have one (Q28 and Q29 have none).

| First expected article at | Questions |
|---|---|
| rank 1 (14) | Q1, Q2, Q5, Q7, Q12, Q14, Q15, Q17, Q18, Q19, Q23, Q24, Q26, Q27 |
| rank 2 to 4 (8) | Q3 (3), Q4 (2), Q9 (2), Q10 (2), Q16 (4), Q20 (2), Q21 (2), Q25 (4) |
| not in the top 5 (5) | Q6, Q8, Q11, Q13, Q22 |

By group: A 4 of 4, B 3 of 5 (Q6, Q8 not found), C 2 of 3 (Q11), D 2 of 3 (Q13), E 6 of 7 (Q22), F 3 of 3, G 2 of 2 with an expected article.

## Question by question (after reading the texts)

| Q | Verdict | What the results show |
|---|---|---|
| 1 | good | L1237-1 first. Ranks 2 to 5 are related: R1237-13 (abandon de poste), L7112-2 (journalists), L1234-x (notice after dismissal). |
| 2 | good | L3121-27 first. Others are weekly limits (youth, 44 and 48 hours). |
| 3 | order wrong | Ranks 1 and 2 are not about paid leave: D3142-82 (giving up rest days), L3121-66 (days worked in a forfait). L3141-3 is third, 0.359 against 0.335 for the first. |
| 4 | order doubtful | Rank 1 is L1242-10, the trial period of a fixed-term contract (CDD), while the question says CDI. L1221-19 second, L1221-21 (renewal) third, which also helps. |
| 5 | good | L1232-2 first, then R1232-2 and L1232-4 (assistance at the meeting). Rank 3 L1233-11 is the same step for economic dismissal. |
| 6 | **miss** | All five are collective rupture (L1237-17, L1237-19-x, D1237-8). L1237-11, the individual rupture conventionnelle, is 48th of 12,136 chunks (0.478). Its text says "convenir en commun des conditions de la rupture", while L1237-17 contains "rupture d'un commun accord". Header check on these two chunks: with and without the header, L1237-11 is 0.478 and 0.480, L1237-17 is 0.414 and 0.441, so the header is not the main cause. |
| 7 | good | L1237-1 first with no accents and no capital. |
| 8 | **miss** | L1221-13 is at distance 0.501 against 0.370 for the 5th result. D1221-23, which cites "l'article L. 1221-13" in its text, is 5th. Header check: with the header L1221-13 is 0.501, without it 0.592, so the article number in the header helps a little but not enough. |
| 9 | good | L1226-9 second. Ranks 1, 3, 4, 5 are the same rule for pregnancy, miscarriage, parental presence leave and birth (L1225-4 to 4-4), which also answer the question for those cases. |
| 10 | good | Rank 1 is L2312-36, the law text that lists the themes of the database; it is as good as R2312-9, which is second. R2312-9 comes back as chunk 1 of 15, the introduction to a table that the other 14 chunks hold. |
| 11 | **miss** | Top 5 are articles on the institution of the conseil de prud'hommes (L1422-1, R1422-2, ...). The annex R1422-4 has 6 chunks of 375 to 446 words, almost only place names, at 0.48 to 0.52. Lyon is in chunk 3 of 6, under "Cour d'appel de Lyon". |
| 12 | good, crowded | Annex R4312-1 is first, but 4 of the 5 places are its chunks (1, 11, 7, 12 of 31); R4312-2 (used machines, refers to the annex) is second. |
| 13 | **partial** | Ranks 1 and 2 are economic dismissal (L1233-15, L1233-7), 3 and 5 protected employees (R2421-13, L2421-3). L1232-1 (the general rule, cause réelle et sérieuse) is 4th, L1232-6 (notification) 7th (0.349 against 0.346 for the 5th), L1232-2 44th, L1232-3 100th. The words "motif personnel" did not steer the results. |
| 14 | good | L1221-21 first, L1221-19 fourth. Rank 2 is the CDD period (L1242-10). |
| 15 | good | Recital 65 first, recital 66 second (also on topic), article 17 third, article 17 in English fifth. |
| 16 | on topic | All five are about consent: article 7, recitals 42 and 32, article 4 (chunk 2 of 3, the one with "11) consentement"), recital 43. The definition is fourth. |
| 17 | good | Article 17 first; recital 66, article 17 (English) and recital 65 follow. |
| 18 | good | Articles 37, 39, 38 first. Ranks 4 and 5 (English recital 80, article 27) are about designating a representative of a non-EU controller. |
| 19 | good | Article 33 first (72 hours), recital 85 second; English copies at 3 and 4; article 34 fifth. |
| 20 | underspecified | Rank 1 is L8115-3: "Le montant maximal de l'amende est de 4 000 euros", labour-code administrative fines, a correct answer to the question as written. GDPR article 83 chunk 2 of 2 (20 million EUR or 4 %) is second; chunk 1 (paragraphs 1 to 4; I did not read it) is not in the top 5. The question does not say RGPD. |
| 21 | on topic | All five are about transfers (recital 101 in English first, article 49, article 48, recital 116, recital 101). Articles 44, 45, 46 are just outside (0.312, 0.320, 0.307 against 0.302). |
| 22 | near miss | Article 3 (0.383) and recitals 22 and 23 (0.398, 0.386) are outside. The five are about harmonisation (recital 13), transfers (recitals 101, 115), one fragment of article 47 (chunk 3 of 4, points m and n of a list) and recital 25. |
| 23 | good | English article 33 first; the rest is English too (recitals 85, 86, article 34, recital 74). |
| 24 | good | English question, French text: L3121-27 first. |
| 25 | found at 4 | Ranks 1 to 3 are off topic (D4163-32 pénibilité account control, R4722-12 chemical exposure control, D7342-6 data of platform workers). Article 88 (employee data) is 4th in French and 5th in English. The Code du travail articles I expected are far: L1222-4 is 1,133th of 12,136, L1121-1 4,738th; the corpus has no article about e-mail. GDPR recital 155 (rules for employee data) is 31st. |
| 26 | good | L3121-27 first despite the false premise. |
| 27 | good | L3141-3 first, then L3141-17, D3142-82, L3164-9, L3142-4. L3142-1 (family leave) is just outside (0.355). |
| 28 | no answer | No hourly SMIC amount in the corpus. Rank 1 D3231-6 (which hourly wage to use) is on the SMIC; the others hold other euro amounts (D5122-13: 8,46 euros, D5522-16: 7,62 euros, D5424-74: 26,30 euros a day). An answer step could mistake them for the SMIC. |
| 29 | no answer | Theft is not in the corpus. Results are penal articles of the labour code (L8234-1 marchandage, L1255-14 portage salarial, L4743-2). |

## Observations across questions

- **Order inside the top 5 is fragile.** The distances of the 5 results lie in a narrow band (about 0.32 to 0.37), and the wrong-order cases (Q3, Q4) are 0.02 to 0.03 apart. A reranker is the usual answer; to be measured in 0c.
- **Everyday words and the legal term.** Q6 and Q25 show the gap between a question in everyday words and the statute's vocabulary. Q13 shows that "personnel" and "économique" dismissals, which share most of their words, are not told apart.
- **Header effect is mixed.** For Q8 the header helps L1221-13 (0.592 to 0.501). For Q3 it hurts L3141-3 (0.342 without the header, 0.359 with) and helps D3142-82 (0.374 without, 0.335 with); that header repeats "Section 2 : Durée du congé" twice. These are three pairs of chunks, so a lead for the header experiments of 0c and not a finding.
- **Both languages in one list.** For French questions 8 English GDPR chunks appear in the top 5 lists, as copies of the French result (for example article 17 and article 33). An English question returns English chunks only (Q23).
- **Long annexes crowd the list** (Q12) and are hard to find by a detail inside (Q11).
- **Split articles.** Q10 finds R2312-9 through its first chunk; Q16 finds article 4 through the chunk that holds the definition (chunk 2 of 3); Q20 finds the second chunk of article 83.
- **Distance and no answer.** The first result's distance is 0.232 to 0.383 where an expected article was found. Q6, Q11 and Q25 (0.414, 0.425, 0.415) and the two unanswerable questions (0.445, 0.459) are above 0.40, but Q8, Q13 and Q22 (0.337 to 0.356) are not. Five questions above 0.40: a hint for the refusal rule of 0d, not a threshold.
- **Close to the top 5, not in it.** Q13 (L1232-6), Q21 (articles 44 to 46) and Q27 (L3142-1) are within 0.005 to 0.05 of the 5th result.

## Expected lists to review before they become an evaluation set

The YAML is unchanged so far. After reading the texts I would add, or reconsider:
- Q10: add L2312-36.
- Q13: add L1232-1; the three listed steps are far down.
- Q15: add recital 66.
- Q16: articles 7 and recitals 32, 42, 43 are on topic; article 4 stays the definition.
- Q20: the question is underspecified between the two sources; L8115-3 is a valid answer.
- Q21: add recitals 101 and 116 as on-topic context, or keep only articles 44 to 49.
- Q25: article 88 is the one that concerns employees; recital 155 fits; L1222-4 and L1121-1 are my legal reading and no result supports them; GDPR article 6 is general.
- Q22: article 3 does answer (paragraph 2 on non-EU controllers offering services to people in the Union).

## What to look at in 0b and 0c

- Exact article references (Q8): keyword search or a direct lookup by number.
- Everyday words (Q6, Q22, Q25): query rewriting, a reranker, or both.
- Annex tables (Q11) and long annexes (Q12): annex handling and chunk size experiments; per-article grouping of results.
- French and English chunks together: a language filter or one unit for both; the index only searches a short candidate list before it applies a filter (see `EXPERIMENT.md`, 2026-10-26).
- Index setting: `hnsw.ef_search` (see below).
- Header variants (Q3, Q8).
- Close calls (Q3, Q4, Q16, Q20): reranker.

## Limits of this test

29 questions chosen by one person; one embedding model; top 5 only; the expected lists are my reading of the law and not a lawyer's; the distance remarks rest on a handful of questions.
