# Handoff: embed the chunking variants on the Windows laptop and publish them

Written 2026-10-29 on the Mac. For an agent (or the user) on the Windows laptop. Facts marked "unverified" come from memory, not from a check. Read `CLAUDE.md` first (working rules). The setup is the same as for Loop 3 (`docs/handoff/loop3_windows_embedding.md`, sections 4 and 5).

## 1. What this is and why
Step 0c compares ways to chunk the text before embedding. Each variant changes one setting of the baseline and needs its own vectors. The Mac cannot embed them in reasonable time (about 12,000 chunks per variant); the Loop 3 baseline took 97 seconds on this laptop (RTX 3060, peak VRAM 1.5 GB).

Five variants, defined in `src/legalrag/variants.py` (the baseline is `default` and already exists):

| Variant | What changes against the baseline | Chunks expected |
|---|---|---|
| `header-none` | no heading line before the text | 12,117 |
| `header-label` | heading with the article label only, no section titles | 12,123 |
| `header-full` | heading with the whole section path | 12,160 |
| `header-collapse` | last 3 section titles, repeated levels merged | 12,135 |
| `size-512` | articles are split above 512 tokens instead of 1,024 | 12,885 |

The expected counts were computed on the Mac on 2026-10-29 from the same code and raw files; the baseline is 12,136. A different count means different raw files or code: stop and report.

## 2. Rules
- The repository and its Releases are public. This job may publish **only** the vectors of the Code du travail and the GDPR (public texts; decision of 2026-10-22). Never publish BSARD, Syntec or anything else under another licence.
- Never commit vectors, raw data, `.env` or keys. `data/` is gitignored; keep it that way.
- Do not edit chunking or embedding code to make a run pass. If a check fails, stop and report the exact output.
- You publish exactly one Release, `embeddings-bge-m3-variants-v1`, with the command in section 5. Do not delete or overwrite the existing release `embeddings-bge-m3-main-v1`.
- No other repository change is expected. If you think a code change is needed, describe it to the user.
- The user's global rules (commit messages, delete commands) are in `docs/handoff/global_CLAUDE.md`.

## 3. Setup
1. `cd ~/legal-rag-eval-fr && git pull`. Check that `src/legalrag/variants.py` exists and run `git log --oneline -1`; note the hash.
2. `uv sync --extra embed`; `uv run python -c "import torch; print(torch.cuda.is_available())"` must print `True`.
3. Raw data present and checked: `make fetch` should print `present` four times (it downloads what is missing and verifies the checksums). `make verify SOURCE=legi` and `make verify SOURCE=gdpr` must pass.
4. `uv run pytest -q` should pass (171 tests on the Mac on 2026-10-29; tests that need files not present on this laptop are skipped).
5. The working tree must be clean (`git status --short` prints nothing). The embedding command records the git commit in each run file, and the publish step refuses a dirty tree.

## 4. Embed
Trial on one variant first (about 40 chunks, under a minute plus model loading):
```
uv run --extra embed legalrag embed --variant header-none --limit 40
```
Expected last line: `40 rows written, 40 computed in …s`. The trial writes small files with the final name; the full run below recomputes and overwrites them (the run record has `"limit": 40` and the publish step refuses it).

Then all five variants (about 2 minutes each plus loading, so roughly 10 to 15 minutes; unverified):
```
make embed-variants
```
- Each variant prints `<N> chunks` first. Compare with the table in section 1.
- It prints `embedded K/N` while running and ends each variant with `<N> rows written, <N> computed in <S>s`.
- If it stops, run `make embed-variants` again: finished shards in `data/embeddings/bge-m3-<variant>/` are kept and skipped.
- Out of memory is not expected (1.5 GB peak in Loop 3). If it happens, stop and report; do not change the batch size.
- Keep the laptop plugged in with sleep disabled.

Output per variant in `data/embeddings/`: `bge-m3-<variant>.parquet` (about 50 MB) and `bge-m3-<variant>.run.json`.

Quick check of each variant (vector norms and the known questions of the Loop 3 sanity check; reads only the files):
```
for v in header-none header-label header-full header-collapse size-512; do uv run --extra embed legalrag sanity --run $v; done
```
Report the output of all five unchanged. A miss on an expected article can be a real effect of the variant (for example without a heading), not a fault, so do not rerun or change anything because of it; a crash or a norm problem is a fault: stop and report.

## 5. Publish
Dry run first. It checks that all ten files exist, that every run record names its variant and settings, that none is a trial run or made from a dirty tree, and that all runs share one commit and one model revision; then it prints the notes with the SHA-256 of every file:
```
make pack-variants
```
If it prints `dry run; would run: gh release create embeddings-bge-m3-variants-v1 (10 files)`, publish:
```
make pack-variants ARGS=--publish
```
This needs `gh auth status` to show a logged-in account with push access to `Labyrintbs/legal-rag-eval-fr` (`gh auth login` otherwise). The release is public by design.

Then confirm: `gh release view embeddings-bge-m3-variants-v1` lists 10 assets.

## 6. Report back
Reply to the user with:
1. `git rev-parse HEAD` of the repo on the laptop.
2. The `<N> chunks` line and the `rows written` line of each variant.
3. The unchanged output of the five `sanity` runs.
4. The dry-run output (the notes with the checksums) and the URL of the release.
5. Anything that did not match this file.

## 7. What happens next on the Mac (not your job)
`gh release download embeddings-bge-m3-variants-v1 -D data/embeddings`, then for each variant `legalrag load-chunks --variant <v>`, `legalrag load-embeddings --variant <v>`, `legalrag db-check --run <v> --expected-chunks <N>`, and `legalrag eval --run <v> --name <v>` on the dev half. Each is compared with the baseline using the paired difference (decision 3b).

## 8. Known effect to keep in mind
A longer heading takes part of the token budget, so the places where long articles are split move a little between header variants (69 split articles in the baseline, 58 with `header-none`, 61 with `header-label`, 83 with `header-full`, 68 with `header-collapse`). The header variants therefore differ in the heading and slightly in the chunk boundaries of those articles. This is recorded in `EXPERIMENT.md`.
