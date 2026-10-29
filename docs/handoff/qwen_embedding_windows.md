# Handoff: embed the chunks with Qwen3-Embedding-0.6B on the Windows laptop and publish them

Written 2026-10-29 on the Mac. For an agent (or the user) on the Windows laptop. Facts marked "unverified" come from memory or a page summary, not from a check. Read `CLAUDE.md` first. Setup, rules and the release routine are the same as in `docs/handoff/variants_windows.md`; this file lists only what differs.

## 1. What this is and why
Step 0c compares embedding models (plan decision D7): the baseline `BAAI/bge-m3` against `Qwen/Qwen3-Embedding-0.6B` (Hugging Face API, 2026-10-29: Apache-2.0, 596M parameters, 1,024-dimension output, sentence-transformers library, 32K tokens). Only the model changes: same chunks (the default chunking, 12,136 chunks), same search. Documents are embedded without an instruction; questions get the model's own `query` prompt ("Instruct: Given a web search query, retrieve relevant passages that answer the query\nQuery:") on the Mac side. The code is in `src/legalrag/embed.py` (`EMBEDDING_MODELS`).

## 2. Rules
Same as `variants_windows.md` section 2: publish only vectors of the Code du travail and the GDPR, never commit data, never edit code to make a check pass, one release only: `embeddings-qwen3-embedding-0.6b-v1`.

## 3. Setup
As in `variants_windows.md` section 3 (git pull, `uv sync --extra embed`, CUDA check, raw files present, clean tree). Two additions:
- `git log --oneline -1` must show a commit that contains `EMBEDDING_MODELS` in `src/legalrag/embed.py` (the `--model` option).
- The model needs `transformers` 4.51 or later (the lock file has a newer one). The first run downloads the weights into `~/.cache/huggingface` (about 1.2 GB, unverified).

## 4. Embed
Trial (about 40 chunks):
```
uv run --extra embed legalrag embed --model qwen3-embedding-0.6b --limit 40
```
Expected last line: `40 rows written, 40 computed in …s`. The full run overwrites these small files.

Full run:
```
make embed-qwen
```
- It prints `12136 chunks` first (the same chunk set as the baseline), then `embedded K/N`, and ends with `12136 rows written, 12136 computed in …s`. Expect a few minutes (unverified; the baseline took 97 seconds).
- Texts are cut at 2,048 tokens of the Qwen tokenizer (the chunks are at most 1,024 bge-m3 tokens).
- If it stops, run `make embed-qwen` again: finished shards in `data/embeddings/qwen3-embedding-0.6b-main/` are kept.
- Out of memory: stop and report (do not change the batch size). The model is about the size of bge-m3, so this is not expected.

Output: `data/embeddings/qwen3-embedding-0.6b-main.parquet` (about 50 MB) and `.run.json` (it holds `"model_key": "qwen3-embedding-0.6b"`).

Quick check:
```
uv run --extra embed legalrag sanity --model qwen3-embedding-0.6b --run main
```
Report the output unchanged. A miss on an expected article can be a real property of the model; a crash or a norm problem is a fault: stop and report.

## 5. Publish
```
make pack-qwen
```
Dry run: checks both files, the run record (model key, default chunking, no `--limit`, clean tree) and prints the notes with the SHA-256 of both files. If it ends with `dry run; would run: gh release create embeddings-qwen3-embedding-0.6b-v1 (2 files)`:
```
make pack-qwen ARGS=--publish
```
Then `gh release view embeddings-qwen3-embedding-0.6b-v1` must list 2 assets.

## 6. Report back
1. `git rev-parse HEAD` of the repo on the laptop.
2. The `12136 chunks` line and the `rows written` line, and the peak GPU memory from the run record.
3. The unchanged `sanity` output.
4. The dry-run notes (with checksums) and the release URL.
5. Anything that did not match this file.

## 7. What happens next on the Mac (not your job)
`gh release download embeddings-qwen3-embedding-0.6b-v1 -D data/embeddings`, `legalrag load-embeddings --model qwen3-embedding-0.6b` into the existing chunking run `default`, then `legalrag eval --embedding-model qwen3-embedding-0.6b --name qwen3` on the dev half and a paired comparison with the baseline.
