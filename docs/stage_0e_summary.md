# Step 0e summary: quality gate in CI

Written 2026-11-11. Decisions and tests: `docs/decisions/0007-step-0e-quality-gate.md`; log: `EXPERIMENT.md`.

## What was built
- **CI** (`.github/workflows/ci.yml`) on every push and pull request, plus a manual button and a weekly Monday run. One job runs ruff, the 348 tests and the gate on a Postgres service; a second job scans the whole git history for secrets (gitleaks).
- **The gate** (`tests/gate/`):
  - **Retrieval floors:** the real search and metrics run on a frozen fixture; Hit@5, Recall@5, Recall@20, MRR@10 and nDCG@10 must stay above `eval/gate_floors.json` (baseline minus 0.02).
  - **Answer replay:** the 65 dev questions go through the real answer engine with the model replaced by its recorded reply; outcome and cited articles must equal the recorded ones.
  - **Repository hygiene:** no `.env`, `data/`, vector or parquet file is tracked.
- **The fixture:** the top 20 articles of each dev question and the gold articles (906 articles, 985 chunks), with vectors. A Release asset (`ci-fixture-v1`), not in git. `make ci-fixture-fetch` and `make gate` run it locally.

## Tested
- The fixture gives the same rankings and metrics as the full database (nDCG@10 0.738, Recall@5 0.800).
- Four deliberate breakages were each caught (search order, worst chunk instead of best, threshold 0.60, units cut to one).
- Passed on Linux x86 with floors set on the Mac. The first CI run also exposed a colour-code problem in one older test; fixed. Latest run green in 48 s.

## Limits
- The gate sees code changes only. A change of embedding model, chunking, prompt or the model itself is not seen: the full evaluation stays a manual step.
- The replay uses recorded replies, so it does not test the model's behaviour.
- Two tokenizer tests skip in CI. No branch protection: a red run blocks nothing.
- The test half is not used by the gate.

## Next
Step 0f: the web service and demo page (feedback box, article-number rule on or off, page language, wiring of the limits).
