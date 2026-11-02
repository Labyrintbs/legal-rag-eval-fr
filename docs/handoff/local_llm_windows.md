# Handoff: try a local quantized model on the Windows laptop for the heading sentences

Written 2026-11-02 on the Mac. For an agent (or the user) on the Windows laptop. Self-contained. Facts marked "unverified" come from memory or from search-result summaries, not from a check on this laptop; **finding out which of them are true is the job**. Read `CLAUDE.md` first (working rules).

## 1. What this is and why
Step 0c has an experiment: an LLM writes one plain French sentence per article, and the sentence goes into the heading that is embedded with the article (plan decision D6, `EXPERIMENT.md`). The full job is about 11,700 articles. The question for this handoff is whether a **small quantized model running on this laptop** can write those sentences well enough and fast enough, instead of the DeepSeek API (about 1 USD for the whole corpus, my estimate).

The plan (D10) only reserved a local model (Qwen3.5-4B, Q4_K_M) for quick developer checks. Everything about running it here was guessed on the Mac. This handoff replaces the guesses with measurements. Nothing is installed or decided yet.

What you produce: a **pilot of 50 articles** through the local model in two or three server configurations, with speed, GPU memory and the output files. The user and the Mac session then read the sentences side by side with DeepSeek's and decide.

## 2. Rules
- The repository is public. Never commit secrets, raw data, embeddings, model files or machine paths (the user name inside `C:\Users\...`).
- The only file you commit is the pilot output (section 8). Each line holds an article id, one generated sentence, flags, timings and token counts, no article text. The script keeps only the build, slot count and context size from the server's `/props` reply, never the model path. Check the file before committing: `grep -ci "users" docs/pilots/*.jsonl` must print 0 for every file.
- Do not edit code to make a step pass. If something fails, stop and report the exact output.
- Ask the user before changing system settings: `%UserProfile%\.wslconfig`, Windows Firewall rules, drivers, the NVIDIA control panel. Describe the change and the way back first.
- Do not download or run any model other than the ones named here, and do not run the full corpus. Those are decisions for the user.
- The user's global rules (commit messages, delete commands) are in `docs/handoff/global_CLAUDE.md`.

## 3. What is already on the Mac (do not redo)
- `scripts/heading_sentence_pilot.py`: draws 50 articles with a fixed seed (40 Code du travail articles, 4 GDPR articles, 4 GDPR recitals, 2 annexes), builds the prompt (`prompts/heading_sentence.yaml`, French; `--prompt sentence.v1` restates the article in plain words, `--prompt sentence.v2` writes the question a worker or employer would ask, in everyday words), sends one article per request, writes `data/pilot/heading_<tag>.jsonl` and prints a summary.
- The same 50 articles went through `deepseek-flash` (backend `deepseek`) with both prompts; the files are in the repository: `docs/pilots/heading_deepseek-flash.jsonl` (v1) and `docs/pilots/heading_deepseek-flash-v2.jsonl` (v2). **The prompt to test on this laptop is v2**; v1 is run once for comparison (8.2 step 6).
- Tests: `tests/test_headsentence.py`.
- The script sends `chat_template_kwargs: {"enable_thinking": false}` so a thinking model does not spend its tokens reasoning (unverified that the server and this model honour it; you will check, see 6.5).

## 4. Hardware and checks first
Hardware from `loop3_windows_embedding.md`: Lenovo Legion R9000P 2021H, Ryzen 7 5800H, RTX 3060 Laptop **6 GB VRAM**, 16 GB RAM, Windows 11 Home.
1. `nvidia-smi` in PowerShell: note the driver version, the CUDA version it shows and the free VRAM. Close other GPU programs (browsers with hardware acceleration use some).
2. Laptop plugged in, sleep disabled, "best performance" power mode.
3. Free disk: at least 6 GB (model about 3 GB, server zip about 0.5 GB).

## 5. Install the server (native Windows, llama.cpp)
Why llama.cpp's `llama-server`: it is a single program, serves an OpenAI-style API on a local port and handles several requests at once (parallel slots with continuous batching, which is on by default; unverified for the current version). Alternatives: Ollama for Windows (one installer, easiest, less control of context and slots; fallback in section 9), vLLM (best throughput, but Linux and heavier setup on 6 GB), plain `transformers` (slowest). I expect llama-server to fit best; confirm by running.

1. Open the releases page of `ggml-org/llama.cpp` on GitHub (the project moved from `ggerganov`; if one redirects, use the other) and pick the newest release.
2. Choose the Windows CUDA zip by the driver from 4.1. A search summary says a build compiled for CUDA 12.x does not work with CUDA 13 and the 13.x build needs a recent driver (580 or later, unverified): driver 580 or later → the `win-cuda-13.x` zip, otherwise the `win-cuda-12.4` zip. Some releases ship the CUDA runtime DLLs as a second zip (`cudart-...`): download it too if `llama-server.exe` complains about a missing DLL (unverified). Do **not** use `winget`: it may install a CPU or Vulkan build (a search summary says so).
3. Unzip to `C:\llama.cpp` (any folder without spaces).
4. `C:\llama.cpp\llama-server.exe --version` prints a build number. Record it and the zip file name.

## 6. Model
### 6.1 Candidate
Qwen3.5-4B, 4-bit `Q4_K_M` GGUF (plan D10: 2.74 GB, Apache 2.0). The Qwen team's own GGUF was not found in a search; community quantizations exist (2026-11-02 search summary): `bartowski/Qwen_Qwen3.5-4B-GGUF` (Q4_K_M about 3.0 GB, imatrix quantization made with llama.cpp build b9222), `SoAIHQ/Qwen3.5-4B-GGUF` (about 2.8 GB), `AlexAtomic/qwen35-4b-GGUF` (about 2.7 GB, says to run with `--jinja`). **Use the bartowski file** (a well-known quantizer, recent llama.cpp): the file is probably named `Qwen_Qwen3.5-4B-Q4_K_M.gguf` (unverified).
1. Open the model page on huggingface.co; note the licence on the card (expected Apache-2.0) and the list of files.
2. Download only the Q4_K_M file into `C:\models` (browser, or `uvx hf download bartowski/Qwen_Qwen3.5-4B-GGUF <file> --local-dir C:\models`). Do not download the vision projector (`mmproj`) file.
3. `Get-FileHash C:\models\<file> -Algorithm SHA256` and the size: put both in the report.

### 6.2 If the model will not load
Qwen3.5 may be a newer architecture than the llama.cpp build knows: the server prints an "unknown model architecture" error. Then: update to the newest llama.cpp release first. If it still fails, stop and report the error; do not pick another model yourself.

## 7. Start the server: three configurations to measure
`<gguf>` is the file from 6.1. Run in PowerShell, one at a time (stop the previous server with Ctrl+C first):

| Config | Command | Why |
|---|---|---|
| A | `C:\llama.cpp\llama-server.exe -m <gguf> --host 127.0.0.1 --port 8080 -ngl 99 -c 4096 -np 1 --jinja` | one request at a time, simplest |
| B | same with `-c 16384 -np 4` | four requests at once; I believe the context is divided between the slots (4,096 each; unverified) |
| C | same with `-c 8192 -np 2` | fallback if B runs out of memory |

- `-ngl 99` asks for all layers on the GPU. The startup log must say all layers were offloaded (the line looks like "offloaded 33/33 layers to GPU", unverified wording) and name the RTX 3060. If it reports 0 layers, the build has no CUDA: stop and report.
- A request needs about 2,000 tokens at most (a 6,000-character article is roughly 1,700 tokens, unverified, plus the prompt and 120 output tokens). If the log shows a slot context under 3,000 tokens, say so in the report.
- Check: `curl.exe http://127.0.0.1:8080/health` prints a JSON status, and `curl.exe http://127.0.0.1:8080/v1/models` shows the model name to pass as `--model` (copy it exactly).

### 7.1 Which context the server really uses
From the log or `curl.exe http://127.0.0.1:8080/props`, note: the context size per slot, the number of slots, and the build. The pilot script records these three values in each output file.

## 8. Run the pilot
The script runs inside WSL2 (where the repository and `uv` are). Preparation in WSL2 (as for the earlier jobs; see `qwen_embedding_windows.md` section 3):
1. `cd ~/legal-rag-eval-fr && git pull`; `git log --oneline -1` (note the hash); `ls scripts/heading_sentence_pilot.py prompts/heading_sentence.yaml` must list both.
2. `uv sync` (the pilot needs no GPU libraries; do not use `--extra embed`).
3. `uv run pytest -q tests/test_headsentence.py` passes. `make fetch` prints `present` four times (raw data is needed to draw the 50 articles).
4. `git status --short` prints nothing.

### 8.1 Let WSL2 reach the server
The server listens on Windows. Try in this order, and stop at the first that works (`curl http://<address>:8080/health` from WSL2 prints the JSON):
1. **Mirrored networking** (Windows 11 22H2 or later, unverified): ask the user, then add `networkingMode=mirrored` under `[wsl2]` in `%UserProfile%\.wslconfig` (keep the existing `memory=` line), run `wsl --shutdown`, reopen WSL2. Then the address is `127.0.0.1`.
2. **Default networking**: start the server with `--host 0.0.0.0` instead of `127.0.0.1`; the Windows address is the default gateway seen from WSL2: `ip route show default | awk '{print $3}'`; Windows Firewall may block port 8080 for the WSL network: ask the user before adding an inbound rule for TCP 8080 (private profile only) and tell them how to remove it.
3. **Run the script in Windows PowerShell** instead (needs `uv` for Windows and the raw files copied there): only if 1 and 2 fail; ask the user.
Never expose the server beyond this laptop: no router port forwarding.

### 8.2 Runs
Replace `<address>` and `<name>` (from `/v1/models`). Open a second terminal for the memory log, started before the run and stopped after it:
```
nvidia-smi --query-gpu=memory.used,memory.total,utilization.gpu --format=csv -l 1 > vram_<tag>.csv
```
1. **Trial** (3 articles, server config A): `uv run python scripts/heading_sentence_pilot.py --backend local --model <name> --base-url http://<address>:8080 --prompt sentence.v2 --n 3 --workers 1 --tag win-trial`. Look at the three sentences in `data/pilot/heading_win-trial.jsonl`. If the sentences contain reasoning text or `<think>` (thinking was not switched off), stop and report: that is the first thing to settle.
2. **Config A**: `... --prompt sentence.v2 --workers 1 --tag qwen35-4b-q4km-v2-np1`.
3. **Config A again** with the same command and the tag `qwen35-4b-q4km-v2-np1-again`, to see whether the same input gives the same sentences (temperature 0).
4. **Config B** (restart the server): `... --prompt sentence.v2 --workers 4 --tag qwen35-4b-q4km-v2-np4`.
5. **Config C** only if B failed (same command with `--workers 2`, tag `...-v2-np2`).
6. **Prompt v1, once**, on the server config that was fastest: `... --prompt sentence.v1 --workers <its slots> --tag qwen35-4b-q4km-v1`. It shows whether the small model follows each prompt equally well.
Each run prints a summary: answered count, flags, wall time, tokens per second. The peak of the second column of `vram_<tag>.csv` is the GPU memory.

### 8.3 Speed of one article alone
From the A run: "server decode speed per call" is the tokens per second of one request. Report it, and the number of seconds per article.

## 9. Fallback if llama.cpp cannot be made to work (ask the user first)
Ollama for Windows (installer from ollama.com). It serves its own API on port 11434 and an OpenAI-style one at `/v1`. The script's field `chat_template_kwargs` is probably ignored there, so thinking models may print their reasoning (unverified); Ollama takes `think: false` in its own API instead. If you go this way, do not edit the script: report what you found and the user decides.

## 10. If something goes wrong
| Symptom | Meaning | Action |
|---|---|---|
| `unknown model architecture` | the build is older than the model | update llama.cpp; if it persists, stop and report |
| log says 0 layers offloaded | no CUDA in this build | wrong zip; try the other CUDA zip; report |
| missing `cudart` or `cublas` DLL | runtime files absent | download the `cudart` zip of the same release |
| `out of memory` at start | context or slots too big | use config C, then A; report which worked |
| `curl` from WSL2 hangs | network path | section 8.1 next option |
| sentences contain `<think>` or reasoning | thinking is on | stop, report the first three outputs |
| HTTP 400 about the context | prompt longer than the slot | report the article id and the slot size |
| slow (under 10 tokens/s on one request) | maybe running on the CPU | check `nvidia-smi` shows a `llama-server.exe` process using memory |

## 11. Report back
Reply to the user with:
1. `git rev-parse HEAD` in WSL2; the llama.cpp zip name and `--version`; the model file name, size and SHA-256; the licence line from the model card.
2. The driver and CUDA version from `nvidia-smi`; which WSL2 network option worked.
3. For each config (A, A again, B, C if run): the server command, the summary printed by the script, the peak GPU memory, and whether the A rerun produced identical sentences (count how many differ).
4. The first five sentences of the A run (copy them), and every flagged line with its flag. Also say, for the v2 run, how many sentences are **not questions** (no question mark) and how many contain a thinking marker.
5. Anything that did not match this file, with the exact output.

Then commit the outputs (names are fixed so the Mac can find them):
```
mkdir -p docs/pilots
cp data/pilot/heading_qwen35-4b-q4km-*.jsonl docs/pilots/
grep -ci "users" docs/pilots/*.jsonl      # must print 0 for every file
git add docs/pilots && git commit -m "Add local heading-sentence pilot outputs" && git push
```
Do not commit the `vram_*.csv` files or the trial files; paste the peak memory numbers in the reply.

## 12. What happens next on the Mac (not your job)
1. The user and the Mac session read the 50 sentences of each model side by side: accuracy to the article text, everyday wording, invented content (for example a "patron" that the article does not mention), article numbers, length.
2. Decision: local model, API, or a mix, with measured speed and cost. If local: the full run is about 11,700 articles at the measured speed; GDPR English needs its own prompt version.
3. The sentence then enters a new chunking run `header-llm` and is embedded on this laptop later (a separate handoff).

## 13. Round 2 (2026-11-02): the 8-bit model and prompt v3
Round 1 (sections 4 to 11) is done and read on the Mac: the 4-bit model runs here at 55 to 59 tokens/s for one request and 25 s for 50 articles with 4 slots, no thinking text, and the same input gives the same sentences on a rerun with one slot. Its weakness is prompt following: with prompt v2 only 14 or 15 of 50 outputs are questions, the rest are statements that often address the reader as "tu" or "ton". The user asked to try the 8-bit version. Because that changes two things at once if run with v2 alone, round 2 is a 2 by 2: model precision (4-bit, 8-bit) against prompt (`sentence.v2`, new `sentence.v3`). v3 asks for a first-person question ending with "?", forbids adding a person the article does not mention, and has one invented example. `git pull` first (the script now accepts `--prompt sentence.v3`); `uv run pytest -q tests/test_headsentence.py` must pass.

Already measured, do not redo: 4-bit + v2 (files `heading_qwen35-4b-q4km-v2-*.jsonl`), 4-bit + v1.

### 13.1 Download the 8-bit file
Same repository as 6.1 (`bartowski/Qwen_Qwen3.5-4B-GGUF`), file probably `Qwen_Qwen3.5-4B-Q8_0.gguf` (unverified), expected 4 to 5 GB (my estimate from one byte per parameter; unverified). Put it next to the other file in `C:\models`; record size and SHA-256. Keep the 4-bit file: it is needed again in 13.3.

### 13.2 Will it fit in 6 GB?
The 8-bit weights alone may fill most of the 6 GB, and Windows itself uses some. Measure, do not assume. Free VRAM from `nvidia-smi` before starting (close browsers and other GPU programs). Start the server in this order and stop at the first failure:
1. **Q8-A**: `C:\llama.cpp\llama-server.exe -m C:\models\<q8 file> --host 127.0.0.1 --port 8080 -ngl 99 -c 4096 -np 1 --jinja`.
2. **Q8-B2**: same with `-c 8192 -np 2`.
3. **Q8-B4**: same with `-c 16384 -np 4`, only if Q8-B2's peak memory left at least 1 GB of the 6 GB free.
All layers must be offloaded (the startup log says how many). If not even Q8-A offloads every layer, **stop and report**; do not lower `-ngl`, do not add KV-cache quantization flags, do not close the display driver: partial offloading makes the speed numbers incomparable and these are decisions for the user.

### 13.3 Runs (50 articles each, one tag per run; memory log as in 8.2 for every server start)
| # | Server | Command tail (after `--backend local --model <name> --base-url http://<address>:8080`) | Tag |
|---|---|---|---|
| 1 | Q8-A | `--prompt sentence.v2 --workers 1` | `qwen35-4b-q8-v2-np1` |
| 2 | Q8-A | `--prompt sentence.v3 --workers 1` | `qwen35-4b-q8-v3-np1` |
| 3 | Q8-B2 or Q8-B4 (the larger that fit) | `--prompt sentence.v3 --workers <its slots>` | `qwen35-4b-q8-v3-np2` or `...-np4` |
| 4 | the 4-bit server, config A (restart with the 4-bit file) | `--prompt sentence.v3 --workers 1` | `qwen35-4b-q4km-v3-np1` |
| 5 | the 4-bit server, config B | `--prompt sentence.v3 --workers 4` | `qwen35-4b-q4km-v3-np4` |
Run a 3-article trial (`--n 3`, tag `win-trial2`) with v3 before run 2 and look at the three sentences: they must be questions ending with "?". Do not rerun anything that already exists. Run 1 twice (second tag `qwen35-4b-q8-v2-np1-again`) only if the first finished within 10 minutes.

### 13.4 Do not
Download any other model or quantization, run the full corpus, change the prompts or the script, or compare the sentences yourself beyond the first look: the Mac reads and counts them.

### 13.5 Report back
1. `git rev-parse HEAD`; the 8-bit file name, size and SHA-256; the licence line is the same as in 11.
2. For each server start: the exact command, the number of offloaded layers, the peak GPU memory from the log (the largest `memory.used`, and the total).
3. For each run: the summary the script prints (answered count, flags, wall time, tokens/s).
4. Which runs you could not do, with the exact error.
Commit the outputs as in section 11, with the new file names:
```
cp data/pilot/heading_qwen35-4b-q8-*.jsonl data/pilot/heading_qwen35-4b-q4km-v3-*.jsonl docs/pilots/
grep -ci "users" docs/pilots/*.jsonl      # must print 0 for every file
git add docs/pilots && git commit -m "Add 8-bit and prompt v3 heading-sentence pilot outputs" && git push
```

### 13.6 What the Mac will do with them
Count questions, "tu/ton" addressing, invented persons, article numbers and flags per run; count the sentences that differ between the 4-bit and 8-bit model for the same prompt; read twelve sentences side by side with DeepSeek's (`docs/pilots/heading_deepseek-flash-v3.jsonl`). The decision is the user's.
