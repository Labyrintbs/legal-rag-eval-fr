# Step 0e: quality gate in CI

Chosen by the user on 2026-11-11 (option 3 of 4): code checks, a retrieval check on a frozen fixture, and an answer-path replay with recorded model replies. The full evaluation (model, GPU, full database) stays a manual step before a release.

Approved by the user on 2026-11-11 (the review gate of 0e).

## What runs on every push (`.github/workflows/ci.yml`)
1. `ruff`, then the whole test suite on a Postgres 16 + pgvector service (the database tests no longer skip).
2. The quality gate, `tests/gate/`:
   - **Retrieval floors.** The real exact search and metric code run on the fixture; Hit@5, Recall@5, Recall@20, MRR@10 and nDCG@10 must stay above `eval/gate_floors.json`.
   - **Answer replay.** The 65 dev questions go through the real answer engine (search, numbering of units, resolver, three refusal layers) with the model replaced by its recorded reply (`tests/fixtures/replies_dev.json`, from `answers_flash-v3.jsonl`). Outcome and cited articles must equal the recorded ones.
   - **Repository hygiene.** No `.env`, `data/`, vector file or parquet outside `tests/fixtures/` is tracked.
3. A secret scan (gitleaks) over the whole history, in a second job.

## The fixture
`scripts/data/make_ci_fixture.py` copies from the full database, for the 65 dev questions, the 20 articles the exact search ranks first and the gold articles (906 articles, 985 chunks), with their vectors and the question vectors. It is a Release asset (`ci-fixture-v1`), never committed (vectors rule). `make ci-fixture-fetch` downloads it; without it the gate skips locally and fails in CI.

## Tested before it was relied on
- Fixture against the full database, same question vectors, 61 dev questions with gold: identical rankings and identical metrics (nDCG@10 0.738, Recall@5 0.800, as in EXPERIMENT.md).
- Floors are the baseline minus 0.02: the search is exact and deterministic, so the margin only absorbs rounding between machines (Mac arm64 here, Linux x86 in CI).
- Four deliberate breakages, each caught: nearest/farthest order of the search, worst chunk instead of best per article (retrieval floors); the weak-retrieval threshold at 0.60 and legal units cut to one (replay).

## What the gate does not see
A change of embedding model, chunking, prompt or the model itself (the replay uses recorded replies), and any real-model behaviour. Those need the full evaluation, run by hand with `make eval` and `scripts/answers/answer_pilot.py`. The test half is not used by the gate.

## Raising a floor
Floors only move in a commit that says why (a better setup measured on dev through the normal process), never to make a failing push pass.

## Triggers
Every push and pull request, a manual button (`workflow_dispatch`), and a weekly run on Mondays at 06:00 UTC. No branch protection is set, so a red run blocks nothing.
