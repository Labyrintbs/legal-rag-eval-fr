# Handoff: embed the `header-llm` chunks with bge-m3 on the Windows laptop and publish them

Written 2026-11-03 on the Mac. For an agent (or the user) on the Windows laptop. Self-contained. Facts marked "unverified" come from memory, not from a check. Read `CLAUDE.md` first (working rules). The setup is the same as for the earlier embedding jobs (`variants_windows.md`, `qwen_embedding_windows.md`).

## 1. What this is and why
Step 0c tests a heading with one LLM-written question per article. The heading of the baseline is "Code du travail, article L1221-13. T1 > T2 > T3." and the new variant `header-llm` adds the question after it: "Code du travail, article L1221-13. T1 > T2 > T3. Puis-je ...?". Only the heading text changes; the chunking limit (1,024 tokens), the search and the questions stay the same. The sentences were written on the Mac by `deepseek-flash` (11,963 of 11,977 articles; 14 sentences that cite an article number are left out and keep the plain heading) and are published as the Release `heading-sentences-v3`. The Mac cannot embed 12,000 chunks in reasonable time; the baseline took 97 seconds on this laptop (RTX 3060 Laptop, peak 1.5 GB).

What you produce: two files, `data/embeddings/bge-m3-header-llm.parquet` and `.run.json`, published as one GitHub Release, `embeddings-bge-m3-header-llm-v1`.

## 2. Rules
- The repository and its Releases are public. Publish **only** the vectors of the Code du travail and the GDPR (public texts; decision of 2026-10-22). Never anything under another licence.
- Never commit vectors, sentences, raw data, `.env` or keys. `data/` is gitignored; keep it that way.
- Do not edit chunking or embedding code to make a run pass. If a check fails, stop and report the exact output.
- Publish exactly one Release, `embeddings-bge-m3-header-llm-v1`. Do not delete or overwrite the existing releases (`embeddings-bge-m3-main-v1`, `embeddings-bge-m3-variants-v1`, `embeddings-qwen3-embedding-0.6b-v1`, `heading-sentences-v3`).
- Do not change the batch size (16) or the sequence length, even after an out-of-memory error: stop and report.
- No other repository change is expected. If you think one is needed, describe it to the user.
- The user's global rules (commit messages, delete commands) are in `docs/handoff/global_CLAUDE.md`.

## 3. Setup (WSL2 Ubuntu)
1. `cd ~/legal-rag-eval-fr && git pull`; `git log --oneline -1` (note the hash). `grep -c "embed-llm" Makefile` must print 1 or more and `grep -c header-llm src/legalrag/variants.py` must print 1 or more.
2. `nvidia-smi` shows the RTX 3060. Close the llama.cpp server and anything else heavy on the GPU (it was used for the local-model pilot).
3. `uv sync --extra embed`; `uv run python -c "import torch; print(torch.cuda.is_available())"` must print `True`.
4. Raw data present and checked: `make fetch` prints `present` four times; `make verify SOURCE=legi` and `make verify SOURCE=gdpr` pass.
5. **Download the sentences** (public Release, 2.9 MB):
   ```
   mkdir -p data/sentences
   gh release download heading-sentences-v3 -D data/sentences
   sha256sum data/sentences/heading-sentences-v3.jsonl
   ```
   The checksum must be `d77bf4c762794a20a472376567ef2fd033fe21204694e8211409e4727681afb8` (also in the release notes). `wc -l` prints 11979. Any other value: stop and report.
6. `uv run pytest -q` passes (tests that need files missing on this laptop are skipped).
7. `git status --short` prints nothing. The run record stores the git commit and the checksum of the sentences file, and the publish step refuses a dirty tree.

## 4. Embed
**Trial first** (about 40 chunks, under a minute plus model loading):
```
uv run --extra embed legalrag embed --variant header-llm --limit 40
```
Expected last line: `40 rows written, 40 computed in …s`. The trial writes small files with the final name; the full run overwrites them (the trial's run record has `"limit": 40` and the publish step refuses it).

**Full run:**
```
make embed-llm
```
- Prints `12150 chunks` first (the baseline has 12,136; the longer heading splits 76 articles against 69). Any other number means different raw files, code or sentences: stop and report.
- Prints `embedded K/N` per shard of 1,000, longest chunks first.
- Ends with `12150 rows written, 12150 computed in …s`. Expect about two minutes (unverified; the baseline took 97 s).
- If it stops, run `make embed-llm` again: finished shards in `data/embeddings/bge-m3-header-llm/` are kept and skipped.

**Check:** `ls -la data/embeddings/bge-m3-header-llm.*` shows a parquet of about 50 MB and the `.run.json`, which must contain `"variant": "header-llm"`, `"limit": null`, the commit hash from step 3.1 without the text "uncommitted", and `"sentences_sha256"` equal to the checksum in step 3.5.

## 5. Publish
Dry run first. It checks both files, the run record (variant, model key, no `--limit`, clean tree, the checksum of the sentences file) and prints the notes with the SHA-256 of both files:
```
make pack-llm
```
If the last line is `dry run; would run: gh release create embeddings-bge-m3-header-llm-v1 (2 files)`, publish:
```
make pack-llm ARGS=--publish
```
This needs `gh auth status` to show an account with push access to `Labyrintbs/legal-rag-eval-fr`. The release is public by design. Then `gh release view embeddings-bge-m3-header-llm-v1` must list 2 assets.

## 6. If something goes wrong
| Symptom | Meaning | Action |
|---|---|---|
| `torch.cuda.is_available()` prints `False` | the PyTorch wheel has no CUDA | stop, report |
| `…heading-sentences-v3.jsonl is missing` from `embed` | step 3.5 not done | download it |
| checksum differs from the one in 3.5 | another version of the file | stop, report both values |
| chunk count is not 12150 | raw files, code or sentences differ from the Mac | stop, report the count and `git log --oneline -1` |
| out of memory | not expected (the model and batch size are the baseline's) | stop, report; do not change the batch size |
| dry run refuses | dirty tree, trial run, or sentences checksum mismatch | clean the cause without editing code, rerun `make embed-llm`, then the dry run again |
| `gh release create` fails | missing permission or the release exists | report the exact output; delete nothing |

## 7. Report back
Reply to the user with:
1. `git rev-parse HEAD` on the laptop.
2. The `12150 chunks` line, the `rows written` line, and the peak GPU memory from the run record.
3. `rows_by_corpus` from the run record.
4. The dry-run notes (with checksums) and the release URL.
5. Anything that did not match this file.

## 8. What happens next on the Mac (not your job)
1. `gh release download embeddings-bge-m3-header-llm-v1 -D data/embeddings`; check the two SHA-256 against the release notes.
2. `legalrag load-chunks --variant header-llm` (the chunks, with the same sentences file), then `legalrag load-embeddings --variant header-llm`, then `legalrag db-check`.
3. `legalrag eval --run header-llm --name headerllm` on the dev half, then `legalrag compare baseline headerllm`, with the split by who wrote the question (the sentences and 30 of the dev questions come from the same model family).
4. Decision rule (3b): `header-llm` replaces the baseline heading only if nDCG@10 clearly rises (paired 95% interval above 0) and Recall@10 does not fall by more than its interval. The test half stays closed until the end of 0c.
