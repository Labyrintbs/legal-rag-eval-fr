# Step 0c summary: retrieval experiments (2026-10-29 to 2026-11-02)

Written 2026-11-02 for the review gate with the project owner. Sources: `EXPERIMENT.md` (every run with its numbers), `docs/decisions/0004-step-0c-decisions.md` (decisions and the test plan).

## Result in one paragraph
Dense search with bge-m3, a heading that holds the document, the article number and the last three section titles, chunks cut at 1,024 tokens and a language filter is the final setup. On the test half it reaches nDCG@10 0.746 [0.649, 0.828] and Recall@10 0.865 [0.772, 0.942] over 64 questions (dev half: 0.738 and 0.893). Every other change we tried was either clearly worse, indistinguishable from the baseline, or a small gain that did not hold up when measured again. No change is part of the final setup.

## How it was done
One change at a time against the same questions, on the dev half (61 gradable questions in 40 clusters). Rule 3b: nDCG@10 must clearly rise (paired 95% interval above 0) and Recall@10 must not clearly fall. The test half was opened once, at the end, with a plan written beforehand: the final setup and five fixed secondary comparisons (four ran; sparse did not reach its threshold).

## Dev results (nDCG@10 change against the baseline, 0.738)
| Ablation | Result | Verdict |
|---|---|---|
| Keyword search BM25, alone / fused | -0.190 / -0.037 to +0.011 | worse / no gain |
| Postgres ts_rank, alone / fused | -0.312, -0.246 / -0.064 to -0.003 | worse than BM25 |
| bge-m3 sparse, alone / fused | -0.099 / -0.006 to +0.029 | no gain; best fused +0.029, below the +0.03 test threshold |
| Heading: none, label only | -0.071, -0.060 | clearly worse |
| Heading: last 2, full path, merged repeats | no difference | baseline (last 3) kept |
| Chunk limit 512 tokens | +0.002 | no difference |
| Embedding Qwen3-Embedding-0.6B | +0.033 [-0.036, +0.106] | no gain |
| Reranker bge-v2-m3 / Qwen3-Reranker (top 50) | +0.055 / +0.061 [+0.003, +0.125] | only Qwen passed 3b, barely |
| Embedding x reranker matrix (6 cells) | one passed (bge-m3 + Qwen3-Reranker) | not a real gain |
| Annexes | not run | kept; one dev question depends on one |
| Language filter off | -0.002 | filter kept |
| Article-number rule | +0.016 [0.000, +0.056], one question | off, noted |
| Query rewriting: replace / fused with original | -0.011 / +0.010 | no gain |
| LLM-written question in the heading (`header-llm`) | +0.035 [-0.025, +0.097]; with keyword fusion +0.048 | no gain; helps keyword search clearly (+0.129 alone) |

## Test half
| | nDCG@10 | Recall@10 | change in nDCG@10 [95%] |
|---|---|---|---|
| Final setup | 0.746 | 0.865 | |
| Qwen3-Reranker | 0.765 | 0.896 | +0.019 [-0.063, +0.101] |
| Rewrite fused | 0.766 | 0.880 | +0.021 [+0.005, +0.041] |
| header-llm | 0.781 | 0.927 | +0.036 [-0.017, +0.094] |
| Article-number rule | 0.746 | 0.865 | 0.000 (no test question names an article) |

The reranker's dev pass did not repeat. Rewriting passes 3b nominally but moved 8 of 64 questions, and its predicted beneficiaries (everyday-wording sheets) did not change. `header-llm` repeats its dev figure and raises Recall@10 clearly. With four comparisons, about a 19% chance that one passes by luck; none of them changes the setup.

## What we learned
- A strong dense model with a good heading is hard to beat on this question set; the heading matters (removing it costs 0.06 to 0.07).
- Word matching alone is weak here (BM25, ts_rank, sparse all clearly below dense); learned weights (sparse) beat BM25, and an LLM question in the text helps it, but fusion does not beat dense.
- Rerankers and rewriting move few questions and the gains are small and unstable; the reranker costs 90 s per question on a CPU against 0.4 s for the whole dense search.
- Faults found and fixed on the way: an annex label bug that made annexes unrankable (invalidated a first reranker result), a window that cut long chunks, a slow Qwen scorer. They show why numbers must be checked against the data before they are believed.
- Small local models (Qwen3.5-4B at 4 and 8 bits on a 6 GB GPU) follow a good prompt but get the content wrong too often to write the heading sentences; DeepSeek did it for 0.75 USD.

## Caveats
- The dev half is small (61 questions) and was used for about forty comparisons; the test half has 64 gradable questions. Intervals are unadjusted.
- Almost all questions are French (2 English, in the test half); English behaviour is untested.
- DeepSeek wrote both the heading sentences and part of the questions: results for `header-llm` are split by who wrote the question, and the gain is not confined to the DeepSeek-written ones.
- The eval set itself was checked by a model and by the owner on a sample (decisions of 0b).

## Costs
LLM 2.55 USD in total (question work 1.78, sentences 0.75, other 0.02). The laptop GPU did the vectors (a few minutes per variant). The Mac CPU did the reranker runs (about 100 minutes each).

## Left open
- The approximate vector index finds 84.9% of the exact neighbours (98% wanted): fix before a service uses it (`0005`). The evaluation uses the exact scan.
- Possible small gains, set aside by decision: Qwen3-Reranker, rewriting, `header-llm`, the article-number rule, bge-m3 sparse fusion. If one is wanted later it needs new questions to be judged fairly.
- No dev or test question tests an article-number query beyond one dev case.

## For the review gate
Approve (or change): the final setup above; the set-aside list; the caveats. Then step 0d (cited answers, refusal on weak retrieval, tracing, rate limits, kill switch, answer-quality evaluation) can start. Step 0f (web service and demo page) is already in the plan.
