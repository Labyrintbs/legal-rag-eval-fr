# Handoff: BSARD sanity run on the Windows laptop

Written 2026-10-29 on the Mac. For an agent (or the user) on the Windows laptop. Facts marked "unverified" come from memory or a page summary, not from a check. Read `CLAUDE.md` first (working rules), then this file.

## 1. What this is and why
BSARD is a public French legal retrieval set: 22,633 Belgian statutory articles and 222 test questions, each labelled with the relevant articles (on average 4.8, at most 57). Running our evaluation code on it checks the harness (metrics, ranking) against a set with published results. It does not test our own corpus.

The job: embed the 22,633 articles with bge-m3, rank them for the 222 test questions, print and save the metrics. The embedding needs the GPU. The Mac would need hours (unverified estimate: about one text per second on CPU); the Loop 3 run embedded 12,136 chunks in 97 seconds on this laptop (`data/embeddings/bge-m3-main.run.json` on the Mac: RTX 3060 Laptop, peak VRAM 1.5 GB, batch 16).

## 2. Rules for this job
- The data is CC BY-NC-SA 4.0 (dataset card on Hugging Face). Use it locally. **Never commit or push the BSARD files, the vectors or the output folder, and never upload them to GitHub, not even as a Release asset.** `data/` is gitignored; keep it that way.
- Do not change the code to make a number look better. If something fails, stop and report the output.
- Do not edit the expected checksums in `scripts/sanity_bsard.py`. A mismatch means the upstream file changed: stop and tell the user.
- No secrets are needed; the files come from a public Hugging Face URL pinned to one dataset revision.
- The user's global rules are in `docs/handoff/global_CLAUDE.md` (comments, commit messages, delete commands). You should not need to commit anything; if you think a code change is needed, describe it to the user instead.

## 3. Setup (the laptop already ran Loop 3, so most of this should exist)
1. In WSL2 Ubuntu: `cd ~/legal-rag-eval-fr && git pull`. The latest commit must contain `scripts/sanity_bsard.py`.
2. `uv sync --extra embed`, then `uv run python -c "import torch; print(torch.cuda.is_available())"` must print `True`. If not, see section 4 step 6 of `docs/handoff/loop3_windows_embedding.md`.
3. `uv run pytest -q` should pass (the Mac gives 160 passed; tests that need `data/raw` are skipped if the raw files are not on this laptop, which is fine for this job).
4. Disk: about 100 MB for the BSARD files and 50 MB for the vectors. The model weights are cached in `~/.cache/huggingface` from Loop 3.

## 4. Run
Smoke first (10 questions, 300 articles, under a minute on the GPU). It also fetches and checks the two data files:
```
uv run --extra embed python scripts/sanity_bsard.py --smoke --device cuda
```
Expected: `articles.csv: ok`, `questions_test.csv: ok`, `300 articles (12 truncated), 10 questions`, then two metric tables. The numbers are not meaningful (300 articles only). The Mac CPU run gave `hit@5 0.900`, `recall@100 0.939` for the first table; small differences on the GPU (fp16) are normal.

Then the full run:
```
uv run --extra embed python scripts/sanity_bsard.py --device cuda
```
- It prints `embedded N/22633` after every block of 2,000 articles. Expected total: a few minutes (unverified; Loop 3 speed suggests under 10).
- If it stops, run the same command again: finished blocks in `data/external/bsard_out/full/blocks/` are kept and skipped.
- Out of memory: add nothing yourself; tell the user (the batch size is fixed at 16 and used 1.5 GB in Loop 3, so this is not expected).
- Keep the laptop plugged in, with sleep disabled.

The script writes to `data/external/bsard_out/full/`:
- `results.json`: all metrics with intervals for both query variants, plus the settings (dataset revision, model revision, device, number of truncated articles).
- `article_ids.json` and `blocks/block_*.npy`: the vectors (float16), in the same order.

## 5. What the output means
- Two query variants are scored: the question alone, and the question followed by `extra_description` (199 of the 222 questions have one). Which one the BSARD paper used is unverified, so both are reported.
- Documents are embedded as `reference`, a line break, then the article text. Articles longer than 1,100 tokens are cut by the model setting; the script prints how many.
- Relevance is binary (no grades), so every gold article counts as primary. Matching is by article id only; identical texts under different ids are not merged, to stay comparable with the paper.
- Metrics: the seven of `legalrag.metrics` plus Recall@100/200/500 (the cut-offs the BSARD paper reports). Intervals resample single questions (no known grouping), 2000 draws, 95%.
- Published reference points, from search-result summaries (unverified): in the [BSARD paper](https://arxiv.org/abs/2108.11792) BM25 has Recall@100 of 51.3 and the best baseline 74.8. These are different models and possibly a different query format, so they are context, not a pass/fail line. The Mac side reads the result.

## 6. Hand back
1. Pack the output folder. Inside WSL:
   ```
   cd ~/legal-rag-eval-fr/data/external/bsard_out && zip -r ~/bsard_full.zip full
   ```
   (Install `zip` with `sudo apt install -y zip` if missing.) Expected size: about 50 MB.
2. Copy `bsard_full.zip` to the Mac by a private route (USB drive, AirDrop-like transfer, a private cloud folder). Not GitHub.
3. In the reply to the user, paste the console output of the full run (both metric tables and the `articles (N truncated)` line) and the `git rev-parse HEAD` of the repo on the laptop.
4. On the Mac: unzip into `data/external/bsard_out/`, read `results.json`, log the numbers in `EXPERIMENT.md`, and close the BSARD item of step 0b.

## 7. If something does not match
- `sha256 ... differs`: stop, report the file name and both hashes.
- HTTP 403 or 429 from Hugging Face: wait and rerun.
- `ModuleNotFoundError` or `.icloud` files: not expected on Windows; report the exact error.
- The smoke numbers or the full numbers look odd (for example Recall@500 far below 1.0 in the smoke run, or all metrics near 0): do not tune anything; send the console output unchanged.
