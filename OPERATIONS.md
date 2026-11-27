# Operations

How the server stack is run. **Tested** means tried on the Mac on 2026-11-26 or 2026-11-27 (S3 to S6 of `docs/decisions/0009-deployment-stage-plan.md`); **planned** means written down but not yet tried on a server. No address, key or password belongs in this file: the repository is public.

## What runs

`compose.server.yaml` starts three services (`docker compose -f compose.server.yaml ...`; `docker-compose.yml` is the development database and is a different file):

| Service | Image | Reachable from outside |
|---|---|---|
| `proxy` | nginx 1.28, config `deploy/nginx.conf` | port 80 only (443 and certbot come in phase 2) |
| `app` | built from `Dockerfile`, runs `legalrag serve` | no |
| `db` | pgvector 0.8.7 on Postgres 16 | no |

Volumes: `pgdata` (the database) and `models` (the bge-m3 weights, 2.1 GB). Secrets and settings come from `.env` next to the compose file (mode 600 on the server, never in git); `.env.example` lists the names.

## Settings

| Name | Meaning |
|---|---|
| `POSTGRES_PASSWORD`, `TRACE_SECRET` | required. `TRACE_SECRET` keys the daily visitor code; keep it fixed, a new value breaks the continuity of those codes |
| `LLM_API_KEY` (else `DEEPSEEK_API_KEY`), `LLM_BASE_URL`, `LLM_MODEL`, `LLM_THINKING_OFF` | the model provider; all empty means DeepSeek. The model needs a row in `llm.PRICES` (the spending caps count in it); the base URL must be https; the app stops at start otherwise |
| Scaleway values | `LLM_BASE_URL=https://api.scaleway.ai/<project id>/v1`, `LLM_MODEL=deepseek-v4.1-flash-1017`, `LLM_THINKING_OFF='{"reasoning_effort": "none"}'` (tried 2026-11-27). The DeepSeek form `{"thinking": {"type": "disabled"}}` is accepted there but ignored: thinking stays on and its tokens are billed. A provider accepts unknown fields silently, so after any change check that `reasoning_tokens` is 0 in a reply, not only that the call succeeds |
| `HTTP_PORT` | published port of the proxy (default 80; 8080 for a test on a Mac) |
| `CODE_VERSION` | tags the image and the answer cache; a new value starts with an empty cache |
| `EMBED_REVISION` | leave empty: the revision stored with the vectors is used. Set it only for a test database whose vectors carry a placeholder |

The spending cap is `cost_per_day_usd` of `answering/limits.py` (0.10 USD a day for the whole service) and the per-visitor limits are in the same file. Costs are counted in USD; euro prices are converted at `llm.USD_PER` (1.20, a rounded-up snapshot of about 1.12 on 2026-11-26). Check the rate every few months and raise the number if the euro gets close to it, or when the provider's currency changes; a test fails if it is set below 1.12.

Scaleway's billing alerts and monthly budget only notify (the console says they "do not freeze your consumption"), so the daily cap above is the brake for normal use, and the alerts are the warning for a leaked key. Keep an alert at a low level (for example 10% of the budget) as well as the higher ones.

## First start (tested on a Mac, planned for the server)

1. Put `.env` next to `compose.server.yaml` with the names of `.env.example`.
2. Download the weights once into the `models` volume (tested: 13 files, 2.1 GB, about 25 s). The revision is the one stored with the vectors:
   ```
   docker compose -f compose.server.yaml run --rm -e HF_HUB_OFFLINE=0 -e EMBED_REVISION=<revision> app python -c "
   import os
   from huggingface_hub import snapshot_download
   snapshot_download('BAAI/bge-m3', revision=os.environ['EMBED_REVISION'], ignore_patterns=['*.onnx*', 'onnx/*', '*.msgpack', '*.h5', 'imgs/*', 'colbert_linear.pt', 'sparse_linear.pt'])"
   ```
   The revision: `SELECT DISTINCT model_revision FROM chunk_embeddings WHERE model = 'BAAI/bge-m3'` in the database that holds the vectors. Without the weights the app stops after about 11 s with the Hugging Face offline error.
3. `docker compose -f compose.server.yaml run --rm app legalrag migrate`, then load the data (below), then `docker compose -f compose.server.yaml up -d`.
4. `curl http://HOST/health` answers `{"status":"ok", ... "llm_host": "<provider host>"}` (tested: 17 s after `up -d` with the weights present).

**Data (open, decided in phase 2).** The plan (D5) rebuilds from the Release assets: `migrate`, `load-chunks`, `load-embeddings` of the `default` run only, `db-check`. The image holds no raw data, so how those commands reach the server is not settled: a one-off container with the raw files mounted, the same commands run from a laptop through an SSH tunnel, or a dump and restore.

## Deploy and rollback (planned, phase 2)

Deploy: set `CODE_VERSION` to the commit, pull or build that image, `docker compose -f compose.server.yaml up -d`, wait for `/health`, keep the previous tag. Rollback: the same with the previous commit's tag (about ten seconds). `up -d` swaps the containers with a few seconds of downtime, accepted.

**Gate before the link is shared with anyone:** `llm_host` in `/health` must be the provider named on `/privacy` (Scaleway, Paris). DeepSeek's own API is for tests with synthetic questions only. The deploy script checks it; until it exists, check by hand: `curl -s http://HOST/health`.

## Day to day

| Task | Command | State |
|---|---|---|
| Written answers off / on / status (kill switch; search keeps working) | `docker compose -f compose.server.yaml exec -T app legalrag service llm-off` (`llm-on`, `status`) | tested |
| Hourly upkeep: erase the text of ordinary requests after 7 days, delete traces after 30, delete expired cache entries | `docker compose -f compose.server.yaml exec -T app legalrag maintain`, from a timer on the host | planned: `/privacy` is not true until this runs |
| Change the provider | edit the `LLM_*` lines of `.env`, `docker compose -f compose.server.yaml up -d app`, check `llm_host` in `/health` | settings tested; the switch itself not tried on a server |
| Rotate the model key | replace it in `.env`, `up -d app` | not tried |
| Rotate `TRACE_SECRET` | same; visitor codes then differ from the older ones | not tried |
| Change `POSTGRES_PASSWORD` | editing `.env` is not enough for an existing volume (Postgres reads it only at the first start): change it in the database too | not tried |
| Rebuild drill | `make fresh-rebuild` (scratch database, compared with the real one; run on a development machine) | exists |

## Checks from outside (phase 2, from another machine)

Done on a Mac through the proxy, where every request comes from one Docker address (so the first two prove the header is overwritten, not that two visitors are told apart):

- a forged `X-Real-IP` or `X-Forwarded-For` gives the same visitor code as none (tested);
- a 20 kB body gets 413, a 20 kB header 400, a request with both `Content-Length` and `Transfer-Encoding` 400, a stalled body is closed after 10 s (tested);
- `nc -vz SERVER 5432` and the app's port 8000 must fail from the outside; Docker publishes ports around the firewall, so test it, do not assume it (planned);
- all pages and static files answer through the proxy; `/docs` and unknown paths answer 404 (tested).

## Measured on a Mac (arm64, Docker Desktop, 2026-11-26)

Image 2.49 GB (nginx 92 MB); memory after a few searches: app 1.03 GiB, db 55 MiB, proxy 7.6 MiB; first search 1.1 s, then 0.35 to 0.5 s on a 985-chunk test database. Not measured: the peak during `/ask`, the amd64 image beyond CI's build, the full 12,136-chunk database, the real 8 GB server.

## The server itself (trial, phase 2)

Ubuntu 24.04 on an OVHcloud VPS: SSH with a sudo user (root login off), UFW allowing 22, 80 and 443 only, fail2ban on the `sshd` jail, unattended security updates, Docker from Docker's apt repository. The user chose to keep SSH password login on; the reasoning and the date are in decision D12 of `docs/decisions/0009-deployment-stage-plan.md`. Backups (D7), monitoring and heartbeats (D8) and the privacy text (phase 4) are not done yet.
