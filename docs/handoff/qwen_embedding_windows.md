# Handoff: embed the chunks with Qwen3-Embedding-0.6B on the Windows laptop and publish them

Written 2026-10-29, rewritten 2026-10-30 on the Mac. For an agent (or the user) on the Windows laptop. Self-contained: you do not need `variants_windows.md`. Facts marked "unverified" come from memory or a page summary, not from a check. Read `CLAUDE.md` first (working rules).

## 1. What this is and why
Step 0c compares embedding models (plan decision D7): the baseline `BAAI/bge-m3` against `Qwen/Qwen3-Embedding-0.6B` (Hugging Face API, 2026-10-29: Apache-2.0, 596M parameters, 1,024-dimension output, sentence-transformers library, 32K tokens). Only the model changes: same chunks (the default chunking, 12,136 chunks), same search, same questions.

- Documents are embedded **without** an instruction. Questions get the model's own `query` prompt ("Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:"); that part runs on the Mac.
- The Mac cannot embed 12,000 chunks in reasonable time. The bge-m3 baseline took 97 seconds on this laptop (RTX 3060 Laptop, 6 GB VRAM, peak 1.5 GB).
- The code is in `src/legalrag/embed.py` (`EMBEDDING_MODELS`: Hugging Face name, query prompt name, `max_seq_length` 2048). Chunk lengths are counted in bge-m3 tokens (at most 1,024); the Qwen tokenizer cuts at 2,048, which leaves headroom.
- What you produce: two files, `data/embeddings/qwen3-embedding-0.6b-main.parquet` and `.run.json`, published as one GitHub Release.

## 2. Rules
- The repository and its Releases are public. Publish **only** vectors of the Code du travail and the GDPR (public texts; decision of 2026-10-22). Never BSARD, Syntec or anything under another licence.
- Never commit vectors, raw data, `.env` or keys. `data/` is gitignored; keep it that way.
- Do not edit chunking or embedding code to make a run pass. If a check fails, stop and report the exact output.
- Publish exactly one Release: `embeddings-qwen3-embedding-0.6b-v1`. Do not delete or overwrite the existing releases (`embeddings-bge-m3-main-v1`, `embeddings-bge-m3-variants-v1`).
- Do not change the batch size (16) or the sequence length, even after an out-of-memory error: stop and report.
- No other repository change is expected. If you think one is needed, describe it to the user.
- The user's global rules (commit messages, delete commands) are in `docs/handoff/global_CLAUDE.md`.

## 3. Setup (WSL2 Ubuntu, as for the earlier embedding jobs)
1. `cd ~/legal-rag-eval-fr && git pull`. Run `git log --oneline -1` and note the hash. The commit must be `9af4b63` or later (it added `EMBEDDING_MODELS` and the `--model` option): `grep -c qwen3-embedding src/legalrag/embed.py` must print 1 or more.
2. `nvidia-smi` shows the RTX 3060. Nothing else heavy uses the GPU.
3. `uv sync --extra embed`. Then `uv run python -c "import torch; print(torch.cuda.is_available())"` must print `True`. The lock file pins `transformers` 5.20.2; the Qwen model needs 4.51 or later, so nothing to do.
4. Raw data present and checked: `make fetch` prints `present` four times; `make verify SOURCE=legi` and `make verify SOURCE=gdpr` pass.
5. `uv run pytest -q` passes (tests that need files missing on this laptop are skipped).
6. `git status --short` prints nothing. The run record stores the git commit, and the publish step refuses a dirty tree.
7. Disk: about 1.2 GB for the model in `~/.cache/huggingface` (unverified) plus about 50 MB for the output. Laptop plugged in, sleep disabled.

## 4. Embed
**Trial first** (about 40 chunks, under a minute plus model loading):
```
uv run --extra embed legalrag embed --model qwen3-embedding-0.6b --limit 40
```
Expected last line: `40 rows written, 40 computed in …s`. The trial writes small files with the final name; the full run overwrites them (the trial's run record has `"limit": 40` and the publish step refuses it).

**Full run:**
```
make embed-qwen
```
- Prints `12136 chunks` first. Any other number means different raw files or code: stop and report.
- Prints `embedded K/N` per shard of 1,000, longest chunks first (an out-of-memory error would show in the first shard).
- Ends with `12136 rows written, 12136 computed in …s`. Expect a few minutes (unverified; bge-m3 took 97 s, Qwen has a similar size but a longer token cut).
- If it stops, run `make embed-qwen` again: finished shards in `data/embeddings/qwen3-embedding-0.6b-main/` are kept and skipped.
- Out of memory is not expected (the model is about the size of bge-m3). If it happens, stop and report.

**Check:** `ls -la data/embeddings/qwen3-embedding-0.6b-main.*` shows a parquet of about 50 MB and the `.run.json`, which must contain `"model_key": "qwen3-embedding-0.6b"`, `"limit": null` and the commit hash from step 3.1 without the text "uncommitted".

**Quick quality check** (reads the two files and runs the known questions of the earlier sanity check, with the Qwen query prompt):
```
uv run --extra embed legalrag sanity --model qwen3-embedding-0.6b --run main
```
Report the output unchanged. Vector norms must be 1.0 within 1e-3. A miss on an expected article can be a real property of the model, not a fault; do not rerun or change anything because of it. A crash or a norm problem is a fault: stop and report.

## 5. Publish
Dry run first. It checks both files, the run record (model key, default chunking, no `--limit`, clean tree) and prints the notes with the SHA-256 of both files:
```
make pack-qwen
```
If the last line is `dry run; would run: gh release create embeddings-qwen3-embedding-0.6b-v1 (2 files)`, publish:
```
make pack-qwen ARGS=--publish
```
This needs `gh auth status` to show an account with push access to `Labyrintbs/legal-rag-eval-fr` (`gh auth login` otherwise). The release is public by design. Then `gh release view embeddings-qwen3-embedding-0.6b-v1` must list 2 assets.

## 6. If something goes wrong
| Symptom | Meaning | Action |
|---|---|---|
| `torch.cuda.is_available()` prints `False` | the PyTorch wheel has no CUDA | stop, report; the fix is the CUDA index in `pyproject.toml` (see `loop3_windows_embedding.md` section 4 step 6) and needs the user's approval |
| chunk count is not 12136 | raw files or code differ from the Mac | stop, report the count and `git log --oneline -1` |
| `chunks would be truncated at max_seq_length` | a chunk is longer than the model limit | stop, report the message |
| download error from Hugging Face | network or rate limit | rerun; if it persists, report (a `HF_TOKEN` is optional, not required) |
| out of memory | not expected | stop, report; do not change the batch size |
| dry run refuses (dirty tree, trial run, wrong model key) | the run record is not publishable | fix the cause (clean the tree by reporting, never by editing code), rerun the full `make embed-qwen`, then the dry run again |
| `gh release create` fails | missing permission or the release exists | report the exact output; do not delete the existing release |

## 7. Report back
Reply to the user with:
1. `git rev-parse HEAD` of the repo on the laptop.
2. The `12136 chunks` line and the `rows written` line, and the peak GPU memory from the run record.
3. The unchanged `sanity` output.
4. The dry-run notes (with checksums) and the release URL.
5. Anything that did not match this file.

## 8. What happens next on the Mac (not your job)
1. `gh release download embeddings-qwen3-embedding-0.6b-v1 -D data/embeddings`; check the two SHA-256 against the release notes.
2. `legalrag load-embeddings --model qwen3-embedding-0.6b` into the existing chunking run `default`, then `legalrag db-check`. The vectors are stored next to the bge-m3 ones (the table is keyed by chunk and model). The approximate index exists only for bge-m3, so evaluation uses the exact scan for both.
3. `legalrag eval --embedding-model qwen3-embedding-0.6b --name qwen3` on the dev half, then `legalrag compare baseline qwen3`.
4. Decision rule (3b): Qwen3-Embedding replaces bge-m3 only if nDCG@10 clearly rises (paired 95% interval above 0) and Recall@10 does not fall by more than its interval. The test half stays closed until the end of 0c.
5. Qwen3-Embedding can also be fused with bge-m3 or tried with a reranker later; that is a separate decision.
