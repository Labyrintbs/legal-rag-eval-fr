# Handoff: bge-m3 sparse (word weight) vectors for the default chunks, on the Windows laptop

Written 2026-11-02 on the Mac. For an agent (or the user) on the Windows laptop. Self-contained. Facts marked "unverified" come from memory, not from a check. Read `CLAUDE.md` first (working rules). The setup is the same as for the earlier embedding jobs (`header_llm_windows.md`).

## 1. What this is and why
Step 0c has an untried keyword option: **bge-m3 sparse**. The same bge-m3 model that gives the dense vector can also give one non-negative weight per token of a text (a small linear layer, `sparse_linear.pt` from the model repository, on top of the last hidden state, then ReLU; the largest weight of each token id is kept and the special tokens are dropped). A question and a chunk then score the sum of weight products over the tokens they share. It is word matching with learned weights, not meaning matching. The Mac encodes the 65 dev questions; the 12,136 chunks need the GPU. The code is in `src/legalrag/experiments/sparse.py` and the command `legalrag sparse-embed`; checked against the FlagEmbedding code on 2026-11-02.

What you produce: two files, `data/embeddings/bge-m3-sparse-default.parquet` and `.run.json`, published as one GitHub Release, `embeddings-bge-m3-sparse-v1`. The default chunking is the baseline (12,136 chunks), so no sentences file is needed.

## 2. Rules
- The repository and its Releases are public. Publish **only** the weights of the Code du travail and the GDPR (public texts; decision of 2026-10-22). Never anything under another licence.
- Never commit weights, raw data, `.env` or keys. `data/` is gitignored; keep it that way.
- Do not edit code to make a run pass. If a check fails, stop and report the exact output.
- Publish exactly one Release, `embeddings-bge-m3-sparse-v1`. Do not delete or overwrite any existing release.
- Do not change the batch size (16) or the maximum length (1,100 tokens), even after an out-of-memory error: stop and report.
- No other repository change is expected. If you think one is needed, describe it to the user.
- The user's global rules (commit messages, delete commands) are in `docs/handoff/global_CLAUDE.md`.

## 3. Setup (WSL2 Ubuntu)
1. `cd ~/legal-rag-eval-fr && git pull`; `git log --oneline -1` (note the hash). `grep -c sparse-embed Makefile` must print 1 or more, and `ls src/legalrag/experiments/sparse.py scripts/data/pack_sparse.py` must list both.
2. `nvidia-smi` shows the RTX 3060. Nothing else heavy uses the GPU (stop the llama.cpp server if it is still running).
3. `uv sync --extra embed`; `uv run python -c "import torch; print(torch.cuda.is_available())"` must print `True`.
4. Raw data present and checked: `make fetch` prints `present` four times; `make verify SOURCE=legi` and `make verify SOURCE=gdpr` pass.
5. `uv run pytest -q` passes (tests that need files missing on this laptop are skipped).
6. `git status --short` prints nothing. The run record stores the git commit, and the publish step refuses a dirty tree.

## 4. Encode
**Trial first** (about 40 chunks, under a minute plus model loading and a 3.5 kB download of `sparse_linear.pt`):
```
uv run --extra embed legalrag sparse-embed --limit 40
```
Expected last line: `40 rows written in …s`. The trial writes small files with the final name; the full run overwrites them (the trial's run record has `"limit": 40` and the publish step refuses it).

**Full run:**
```
make sparse-embed
```
- Prints `12136 chunks` first (the baseline has 12,136; any other number means different raw files or code: stop and report).
- Prints `encoded K/12136` every 800 chunks, longest chunks first.
- Ends with `12136 rows written in …s`. Expect about two minutes (unverified; the dense baseline took 97 s).

**Check:** `ls -la data/embeddings/bge-m3-sparse-default.*` shows a parquet (a few tens of MB; unverified) and the `.run.json`, which must contain `"variant": "default"`, `"limit": null`, the commit hash from step 3.1 without the text "uncommitted", and `"tokens_per_chunk_mean"` (report it).

## 5. Publish
Dry run first. It checks both files and the run record (default chunking, no `--limit`, clean tree) and prints the notes with the SHA-256 of both files:
```
make pack-sparse
```
If the last line is `dry run; would run: gh release create embeddings-bge-m3-sparse-v1 (2 files)`, publish:
```
make pack-sparse ARGS=--publish
```
This needs `gh auth status` to show an account with push access to `Labyrintbs/legal-rag-eval-fr`. The release is public by design. Then `gh release view embeddings-bge-m3-sparse-v1` must list 2 assets.

## 6. If something goes wrong
| Symptom | Meaning | Action |
|---|---|---|
| `torch.cuda.is_available()` prints `False` | the PyTorch wheel has no CUDA | stop, report |
| error loading `sparse_linear.pt` (size mismatch) | the model layer is not Linear(1024, 1) | stop, report the exact message |
| chunk count is not 12136 | raw files or code differ from the Mac | stop, report the count and `git log --oneline -1` |
| out of memory | not expected (the model is the baseline's) | stop, report; do not change the batch size |
| dry run refuses | dirty tree or trial run | clean the cause without editing code, rerun `make sparse-embed`, then the dry run again |
| `gh release create` fails | missing permission or the release exists | report the exact output; delete nothing |

## 7. Report back
Reply to the user with:
1. `git rev-parse HEAD` on the laptop.
2. The `12136 chunks` line, the `rows written` line, the peak GPU memory (`peak_vram_mb`) and `tokens_per_chunk_mean` from the run record.
3. The dry-run notes (with checksums) and the release URL.
4. Anything that did not match this file.

## 8. What happens next on the Mac (not your job)
1. `gh release download embeddings-bge-m3-sparse-v1 -D data/embeddings`; check the two SHA-256 against the release notes.
2. `legalrag eval --search keyword --lexical sparse --name sparse-keyword` and `--search hybrid --lexical sparse --keyword-weight 1.0 / 0.5 / 0.25` on the dev half, compared with the dense baseline and with BM25 at the same weight. The index refuses a file whose chunks or texts do not match the `default` run.
3. Decision rule (3b): a sparse search replaces dense only if nDCG@10 clearly rises and Recall@10 does not fall clearly. The test half stays closed until the end of 0c.
