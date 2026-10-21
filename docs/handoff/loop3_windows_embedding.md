# Handoff: Loop 3 embeddings on the Windows laptop

Written 2026-10-21 on the Mac, at commit `91b6927`. Read this file fully, then `CLAUDE.md` (working rules) and `EXPERIMENT.md` (every data and chunking change so far). Facts marked "unverified" come from memory, not from a check.

## 1. What this project is
A question-answering service over French labour law (Code du travail) and the GDPR, with measured evaluation. French questions first. Answers will cite articles and refuse when the corpus cannot answer. The corpus is built in step 0a (ingest) in four loops, each ending with a review gate where the user approves before the next one starts:

| Loop | Content | State |
|---|---|---|
| 1 | Code du travail: read, profile, chunk, verify | done and approved |
| 2 | GDPR (French and English): read, profile, chunk, verify | done and approved |
| 3 | Embeddings and storage | **this handoff** |
| 4 | Smoke retrieval (about 10 hand-written questions) | later |

After 0a come the evaluation set (0b), retrieval experiments (0c), answers and guardrails (0d) and a CI quality gate (0e).

## 2. Where Loop 3 is split between the two machines
- **Windows laptop (this handoff, part A):** compute the bge-m3 vectors for every chunk and write them to a file. Nothing else.
- **Mac (part B, later, not your job unless the user says so):** Postgres + pgvector in Docker, schema and migrations, loading chunks and vectors, the vector index, the retrieval checks.

Why the split: the Mac (M1, 16 GB RAM) is slow for this job, the Windows laptop has an NVIDIA GPU. The user decided this; do not benchmark on the Mac.

Hardware of the Windows laptop: Lenovo Legion R9000P 2021H, Ryzen 7 5800H, NVIDIA RTX 3060 Laptop GPU with 6 GB VRAM, 16 GB RAM, Windows 11 Home, 512 GB system SSD. It is not a server: plug it in, disable sleep during the run, watch heat.

## 3. State of the repository
- Repo: https://github.com/Labyrintbs/legal-rag-eval-fr (public; never commit raw data, keys, `.env`, or the embeddings file).
- Python 3.12 with `uv`; `uv sync` installs the light set; `uv sync --extra embed` adds `sentence-transformers` and PyTorch for this job.
- 59 tests pass (`uv run pytest`). `make verify SOURCE=legi` and `make verify SOURCE=gdpr` pass. On Windows use WSL2, where `make` works.
- Code that matters for you:
  - `src/legalrag/sources/legi.py` (Code du travail reader), `src/legalrag/sources/gdpr.py` (GDPR reader, French and English)
  - `src/legalrag/ingest.py`: `build_chunks(articles, count_tokens, style="last_k", k=3, max_tokens=1024, collapse_repeats=False)` returns `Chunk` objects (`src/legalrag/models.py`). The text to embed is `chunk.embed_text` (header, a line break, then the body).
  - `src/legalrag/cli.py`: Typer commands `profile` and `verify`; add the embedding command here.
- Default chunk settings (decisions made, see `EXPERIMENT.md`): one article = one chunk, split only above 1,024 bge-m3 tokens, no overlap, header style `last_k` with k=3, `collapse_repeats` off. Use exactly these defaults for the run; they define the chunk set.
- Expected chunk counts with those defaults: Code du travail 11,563 (from 11,433 articles), GDPR French 292 (from 99 articles and 173 recitals), GDPR English 281. Total 12,136. Largest chunk is 1,023 tokens (counted without special tokens).

## 4. Windows setup (all of this is unverified on this machine)
1. Install WSL2 with Ubuntu (administrator PowerShell: `wsl --install -d Ubuntu`, then restart).
2. Install only the NVIDIA driver on Windows (version 535 minimum, 560 or newer recommended); do not install a driver inside WSL. In Ubuntu, `nvidia-smi` must show the GPU.
3. Cap WSL memory in `%UserProfile%\.wslconfig` (`[wsl2]` then `memory=10GB`), then `wsl --shutdown`.
4. In Ubuntu: `sudo apt update && sudo apt install -y make git`, install uv (`curl -LsSf https://astral.sh/uv/install.sh | sh`), and set up GitHub access for pushing (for example `gh auth login`).
5. Clone inside the Linux filesystem, not under `/mnt/c`: `git clone https://github.com/Labyrintbs/legal-rag-eval-fr.git ~/legal-rag-eval-fr`.
6. `cd ~/legal-rag-eval-fr && uv sync --extra embed`. Then check `uv run python -c "import torch; print(torch.cuda.is_available())"` prints `True`. If it prints `False`, the PyTorch wheel has no CUDA: pin the CUDA index in `pyproject.toml` as described in https://docs.astral.sh/uv/guides/integration/pytorch/ (needs uv 0.5.3 or newer) and record the change in `EXPERIMENT.md`.
7. Run `uv run pytest` and expect 59 passed (the real-tokenizer tests are skipped until the data in section 5 is present).

## 5. Get the raw data
The `data/` folder is not in git. Either copy the four files from the Mac's `data/raw/` or download them. Check the SHA-256 of each (`sha256sum`).

| File in `data/raw/` | SHA-256 | Source |
|---|---|---|
| `legi_vincegx33_train.parquet` (262,688,820 bytes) | `6b4e2fde6daab5fa92bccec533037a33e27f4df353b4f7e647cc356f3018287b` | `https://huggingface.co/datasets/VinceGx33/legi-french-law-2025/resolve/refs%2Fconvert%2Fparquet/default/train/0000.parquet` |
| `gdpr_fr.xhtml` (876,858 bytes) | `27a2248cf0cf7c79a3ec7eae30b6e871817230d9f577632fed915181642144c2` | `curl -sL -A "Mozilla/5.0 (research)" -H "Accept: application/xhtml+xml" -H "Accept-Language: fr" -o data/raw/gdpr_fr.xhtml https://publications.europa.eu/resource/celex/32016R0679` |
| `gdpr_en.xhtml` (806,864 bytes) | `962539af03738bf552319ff4ce42d69e5f95a576307c4dfed7bf87e81b646b9d` | same command with `Accept-Language: en` |
| `bge-m3-tokenizer.json` (17,098,108 bytes) | `21106b6d7dab2952c1d496fb21d5dc9db75c28ed361a05f5020bbba27810dd08` | `https://huggingface.co/BAAI/bge-m3/resolve/main/tokenizer.json` |

If a checksum differs, the upstream file changed. Do not continue silently: run `make verify SOURCE=legi` and `make verify SOURCE=gdpr`; they check the counts and the token statistics, and the expected chunk total in section 3 must still match. Tell the user what changed.

Then `make verify SOURCE=legi` and `make verify SOURCE=gdpr` must both pass before you embed anything.

## 6. The embedding job to build
Add a command `legalrag embed` (Makefile target `make embed`). Design, from the step 0a spec:

- **Model:** `BAAI/bge-m3`, dense vectors only, 1,024 dimensions, MIT licence, via `sentence-transformers`. Normalise the vectors (`normalize_embeddings=True`) so cosine similarity equals a dot product. Record the Hugging Face model revision (commit hash) in the output.
- **Input:** build the chunks inside the job with `build_chunks` and the default settings from section 3, for the three corpora (Code du travail French, GDPR French, GDPR English). Embed `chunk.embed_text` exactly. For bge-m3, queries need no instruction prefix (unverified: confirm on the model card).
- **Truncation trap:** the library adds two special tokens, so a chunk of 1,023 tokens becomes 1,025. Set `max_seq_length` above 1,030 (the default 8,192 also works) and check that no text is truncated.
- **Speed:** use fp16 on the GPU, start with batch size 16 to 32, sort chunks by length to limit padding. The GPU has 6 GB of VRAM: lower the batch size if it runs out of memory. Do not run other GPU jobs at the same time.
- **Resume:** write the output in shards and skip chunks that are already done (same key and same `embed_text_hash`), so an interrupted run can continue. The job is a one-time run of about 12,000 chunks; time and peak VRAM are worth recording in `EXPERIMENT.md`.
- **Output:** `data/embeddings/bge-m3-<run>.parquet` (gitignored), one row per chunk, columns:
  - `article_uid` (for example `code_travail:fr:LEGIARTI000006900853`, `rgpd:fr:art_5`), `chunk_index`, `lang`
  - `model` (`BAAI/bge-m3`), `model_revision`, `dim` (1024)
  - `embed_text_hash` (sha256 of `embed_text`; the Mac recomputes it to be sure both machines built the same chunks)
  - `vector` (1,024 float32 values)
  - Also write a small `run.json` next to it: git commit, chunk settings, library versions, GPU name, counts.
  The key (`article_uid`, `chunk_index`) is used instead of a database id, because the database does not exist on this machine.

## 7. Checks the job must pass
- Row count equals the chunk count (12,136 with the defaults); no duplicate (`article_uid`, `chunk_index`).
- Dimension 1,024; no NaN; vector norm about 1.
- No chunk truncated.
- Sanity test without a database: embed about 5 French questions with the same model and rank all vectors by cosine similarity with numpy. For example "préavis de démission" should return L1237-1 in the top 3, "droit à l'effacement" should return GDPR article 17 in the top 3. These are inspection checks, not a metric.
- Unit tests for the new code in the same style as `tests/test_chunking.py` and `tests/test_gdpr.py`, using a stub embedder so they run without a GPU; the full suite must pass.

## 8. Finish and hand back
1. Log the run in `EXPERIMENT.md` (date, what changed, measured effect: time, VRAM, counts, sanity results, commit hash).
2. Commit the code, tests and docs (not the data), push, and tell the user.
3. The user copies the embeddings file and `run.json` to the Mac (about 50 MB; do not put them in git, the repo is public). A private cloud drive or a direct copy both work.
4. Stop at the review gate: show the user the checks, the sanity results and the timing, and wait for approval.

## 9. What the Mac does afterwards (part B, for context)
Docker Compose with `pgvector/pgvector:0.8.7-pg16` (`make db-up`, tested earlier). Alembic migrations for the accepted schema:
- `corpus_versions`, `articles`, `chunking_runs`, `chunks` (with a keyword-search column `tsv`), `chunk_embeddings` keyed by (chunk id, model) with `vector(1024)`.
- Load articles and chunks, load the vectors by matching (`article_uid`, `chunk_index`) and checking `embed_text_hash`, then build a partial HNSW index with cosine operators for `model = 'BAAI/bge-m3'` (queries must repeat that literal for the planner to use it).
- Checks: the index exists and `EXPLAIN` uses it, row counts match, a known sentence finds its own article. Then Loop 4 (smoke retrieval).

## 10. Open or unverified items you may meet
- CUDA wheel selection with uv on Linux (section 4, step 6) and the bge-m3 prompt convention (section 6).
- Whether the GDPR text includes later corrigenda is unverified; the file is the text as published on 4 May 2016.
- Annexes of the Code du travail are flattened tables; they stay searchable for now and are compared in step 0c.
- The user decides every design choice, one at a time, with options and evidence; see `CLAUDE.md`.
