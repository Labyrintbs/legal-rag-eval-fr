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

Scaleway's billing alerts and monthly budget only notify (the console says they "do not freeze your consumption"), so the daily cap above is the brake for normal use, and the alerts are the warning for a leaked key. Keep an alert at a low level (for example 10% of the budget) as well as the higher ones. The hard limits are in the console under Generative APIs, tab Rate limits (new, found by the user on 2026-11-27; a search of the documentation had missed it): a rate limit per project in tokens per minute for each model (default 7,000,000 for `deepseek-v4.1-flash-1017`, enough to spend about 250 euros an hour if a key leaked) and a daily and a monthly budget per IAM user or application (disabled by default). Lower the project limit and set both budgets for the application that owns the key. Other layers: billing alerts (up to 10, by email, SMS or webhook), and Cockpit for the token use of a project (up to an hour late). A leaked key is stopped by revoking it (IAM, API keys). Values set on 2026-11-27 for `deepseek-v4.1-flash-1017`: project rate limit 50,000 tokens a minute (maximum 7,000,000), daily budget 1 million tokens, monthly budget 5 million tokens (whole millions are the smallest step the console takes). That bounds the worst case at about 1.80 euros a day and 9 euros a month. Not confirmed: that the budget applies to the application that owns the key (the page says "per IAM users or applications"), and what a refused call looks like.

Scaleway billing facts, from a web search of its documentation on 2026-11-27 (its pages refuse automated reading, so each is to be confirmed by reading the page):
- The first 1,000,000 tokens are free, counted over input and output of all models, applied to the most expensive tokens first; whether it is once or monthly, and how cached tokens count, is not stated in what was found. The minimum billing unit is 1,000 tokens in the current FAQ (an older revision said 1 million).
- Invoices are monthly, for the previous month's consumption, paid automatically by the registered method. An invoice unpaid after ten days suspends the account, and ten days later its resources are deleted; a failed payment can then only be settled by card, not by SEPA. Virtual and prepaid cards are reported as not accepted, so a card with its own limit may not be possible.
- The console shows amounts excluding taxes; the VAT rule for a person without a VAT number (local rate, 20% in France) is stated unclearly, so count on 20% more than the table prices.
- `deepseek-v4.1-flash-1017` is a Preview model (confirmed on Scaleway's lifecycle page by the user): no service level agreement, support guaranteed for at least one month from launch, one month of notice before removal; Active models: at least 8 months of support and 3 months of notice before end of life. When a model is removed Scaleway may answer its name with a similar model, with no guarantee that outputs stay similar, so a reply from another model could pass unnoticed (a check on the `model` field of the reply is proposed, not built). Keep the provider a setting and read Scaleway's e-mails.
- From the contract (Specific Conditions of 2026-09-21 and the DPA of 2024-06-01, read 2026-11-27): the quota level of the serverless API depends on a validated payment method and identity verification (KYC), and Scaleway may suspend for "overconsumption"; notice of sub-processor changes (30 days) is sent only to those who subscribed on Scaleway's sub-processor page, so subscribe; the client must check the licence of the third-party model and comply with the EU AI Act as deployer.
- Not found: whether failed requests are billed. Reasoning tokens count in `completion_tokens` (seen in a reply), so they are billed as output when thinking is on.

Tracking the spend (Scaleway). The app side: `legalrag service status` (today's cost against the cap) and `legalrag traces summary` (cost of the answers). The Scaleway side: Billing, tab Consumption (by model), and Cockpit for the project (up to an hour late). Check weekly and after any measurement run. While the free first 1,000,000 tokens last, Scaleway's consumption shows 0 euros: compare token counts (Cockpit against the app's token counts) instead of amounts. Normal: Scaleway's figure is near the app's estimate plus up to 20% VAT, and at most about 3 euros a month at the daily cap. Abnormal: more than twice the estimate, or more than 1 euro in a week when nothing was measured, or an alert at 50%. Then: revoke the application's key (IAM), empty the `LLM_*` settings so the service uses DeepSeek again (with the clear notice on the page, decision D2), and only then decide whether to close the account (closing is blocked while consumption is unpaid). The user pays with a card holding a small balance, which is a hard stop from the card side: the month's invoice (plus VAT) must be covered by the end of the month, or the account is suspended after ten days.

## First start (tested on the server, 2026-11-27)

1. On the server: `git clone https://github.com/Labyrintbs/legal-rag-eval-fr.git legal-rag`, then create `.env` in it (mode 600). The passwords are generated on the server (`openssl rand -hex 16` for `POSTGRES_PASSWORD`, `openssl rand -hex 24` for `TRACE_SECRET`), `HTTP_PORT=127.0.0.1:8080` keeps the proxy private (reachable only through an SSH tunnel until the public step), `CODE_VERSION` is the short commit, and the `LLM_*` lines are copied from the laptop's `.env` over SSH without printing them (`grep '^LLM_' .env | ssh SERVER 'cat >> legal-rag/.env'`).
2. Build: `sudo docker compose -f compose.server.yaml build app` (tested: 154 s, image 2.62 GB for amd64).
3. Download the weights once into the `models` volume (tested: 13 files, 2.1 GB, 14 s). The revision is the one stored with the vectors:
   ```
   sudo docker compose -f compose.server.yaml run --rm -e HF_HUB_OFFLINE=0 -e EMBED_REVISION=<revision> app python -c "
   import os
   from huggingface_hub import snapshot_download
   snapshot_download('BAAI/bge-m3', revision=os.environ['EMBED_REVISION'], ignore_patterns=['*.onnx*', 'onnx/*', '*.msgpack', '*.h5', 'imgs/*', 'colbert_linear.pt', 'sparse_linear.pt'])"
   ```
   The revision: `SELECT DISTINCT model_revision FROM chunk_embeddings WHERE model = 'BAAI/bge-m3'` in a database that holds the vectors. Without the weights the app stops after about 11 s with the Hugging Face offline error.
4. Load the data with the documented commands, run from the laptop through an SSH tunnel (the image holds no raw data; this keeps the tested path of the README). On the server, publish the database on its localhost only, through a temporary override file kept outside the repository: `printf 'services:\n  db:\n    ports:\n      - "127.0.0.1:5432:5432"\n' > /tmp/db-local.yaml` and `sudo docker compose -f compose.server.yaml -f /tmp/db-local.yaml up -d db`. On the laptop: `ssh -f -N -L 15432:127.0.0.1:5432 SERVER`, then with `DATABASE_URL=postgresql://legalrag:<password>@127.0.0.1:15432/legalrag` run `legalrag migrate`, `legalrag load-chunks` (36 s), `legalrag load-embeddings` (11 s, builds the index) and `legalrag db-check` (tested: all 11 checks pass, the same numbers as the laptop). Then close the tunnel, delete the override and run the deploy, which recreates the database without the port.
5. `deploy/deploy.sh` (below). `curl http://127.0.0.1:8080/health` on the server answers `{"status":"ok", ... "llm_host": "api.scaleway.ai", "llm_failing": false}`.

## Deploy and rollback (`deploy/deploy.sh`, run on the server in the repository folder)

- `deploy/deploy.sh [REF]` fetches, checks out REF (default `origin/main`), builds the image tagged with the commit, starts the stack, waits up to 3 minutes for `/health` through the proxy, and checks that `llm_host` is one of `ALLOWED_LLM_HOSTS` (default `api.scaleway.ai`). `.deploy-state` keeps the current and the previous tag (git-ignored).
- **The provider gate:** if `llm_host` is not allowed, the script stops the proxy and exits with code 2: the link must not be shared while the stack points to another provider (DeepSeek's own API is for tests with synthetic questions only; see the plan, D2).
- A start that is not healthy goes back to the previous tag by itself (exit code 1). `deploy/deploy.sh rollback` starts the previous tag again, with no build; images are kept by tag. `up -d` swaps the containers with a few seconds of downtime, accepted.
- Tested on the server on 2026-11-27: the first deploy (health ok, provider allowed, "deployed"); a disallowed provider (exit code 2, proxy stopped, state unchanged); a normal deploy of a second commit (state `new previous`); `rollback` (back to the first commit's image, state swapped); a deploy again. Not tried: a start that is not healthy (the automatic return to the previous tag).

## Day to day

| Task | Command | State |
|---|---|---|
| Written answers off / on / status (kill switch; search keeps working) | `docker compose -f compose.server.yaml exec -T app legalrag service llm-off` (`llm-on`, `status`) | tested on the Mac and on the server (503, `llm_disabled`, the five articles still shown, `/search` still 200) |
| Hourly upkeep: erase the text of ordinary requests after 7 days, delete traces after 30, delete expired cache entries | `docker compose -f compose.server.yaml exec -T app legalrag maintain`; scheduled on the server by `/etc/cron.d/legalrag-maintain` (minute 17 of every hour, output to syslog under `legalrag-maintain`) | tested 2026-11-27: run by hand and as cron runs it (root, minimal environment); no heartbeat yet, so a failing run is not noticed (phase 3) |
| Change the provider | edit the `LLM_*` lines of `.env`, `docker compose -f compose.server.yaml up -d app`, check `llm_host` in `/health` | settings tested; the switch itself not tried on a server |
| Rotate the model key | replace it in `.env`, `up -d app` | not tried |
| Rotate `TRACE_SECRET` | same; visitor codes then differ from the older ones | not tried |
| Change `POSTGRES_PASSWORD` | editing `.env` is not enough for an existing volume (Postgres reads it only at the first start): change it in the database too | not tried |
| Rebuild drill | `make fresh-rebuild` (scratch database, compared with the real one; run on a development machine) | exists |

## Backups (phase 3, decision D7; tested on the server on 2026-11-27)

- **What:** `deploy/backup.sh` (run on the server, as root; cron `/etc/cron.d/legalrag-backup`, 02:30 UTC, output to syslog under `legalrag-backup`) copies (1) a `pg_dump` of the tables `alembic_version articles chunk_embeddings chunking_runs chunks corpus_versions service_flags` and (2) `.env`, `.deploy-state` and `/etc/cron.d/legalrag-maintain`. restic encrypts on the server (passphrase `BACKUP_PASSPHRASE`) and sends the pieces to the bucket `legalrag-backup-7k3q9x` (Scaleway Object Storage, Paris, project `legalrag-demo`, private; versioning, object lock and bucket encryption off). Keeps 7 daily and 4 weekly copies per kind.
- **Not copied, on purpose:** `query_traces` and `answer_cache` (visitors' questions and the answers to them: `/privacy` keeps them 7 to 30 days, a backup would keep them longer). A new table is not copied until it is named in the script; a test (`tests/deploy/test_backup.py`) fails when a migration adds a table that is in neither list. The articles, chunks and vectors can also be reloaded from the repository and the release files (about 36 s), but the dump restores without the Mac.
- **Credentials:** the application `legalrag-backup` (IAM policy `legalrag-backup`: ObjectStorageObjectsRead, ObjectsWrite, ObjectsDelete, BucketsRead, scope: project `legalrag-demo`); its key is limited to Object Storage and cannot reach the model; the model's application `legalrag-api` cannot reach the bucket. No bucket policy. The key is in the server `.env` and the owner's local `.env`; the passphrase is also in the owner's password manager.
- **Second copy:** the Scaleway contract (Specific Conditions for Storage, 2026-04-07) gives no durability guarantee ("eleven nines" is theoretical) and tells the client to keep several backups: a copy on the owner's Mac is still to be arranged. The OVH automatic backup of the whole VPS (daily, one restore point, on by default, seen in the control panel) is a free extra; it also contains the traces table, so it holds visitors' text for up to a day beyond the rules above (to name on `/privacy`).
- **Drill:** `deploy/backup.sh restore` restores the latest dump into a scratch database `legalrag_restore_check` in the same Postgres, runs `ANALYZE`, compares the row count of every table with the live one, runs `legalrag db-check` against the copy and drops the scratch database. Done on 2026-11-27: all counts equal; `db-check` 11 of 11 passed. The first try failed one check (the planner did not use the HNSW index) because a restored database has no statistics until `ANALYZE`: after any restore run `ANALYZE` before the service starts.
- **Size and time:** the dump is about 63 MiB; the repository holds about 2 MiB of new data per further copy that changed little; a backup takes about 30 s; checked with `restic check --read-data-subset=100%` (no errors).
- **Restore on a new server (database part rehearsed, the rest not):** install Docker and restic, clone the repository, put the six `BACKUP_*` lines and `POSTGRES_PASSWORD` in `.env` (from the local `.env` and the password manager), `restic restore latest --tag config --target /tmp/r` for the other files, start the `db` service, `CREATE EXTENSION vector` in the empty database, `restic dump latest --tag db /var/tmp/legalrag-backup/legalrag.dump | docker compose exec -T db pg_restore -U legalrag -d legalrag --no-owner`, `ANALYZE`, then `deploy/deploy.sh`.
- **Not done yet:** the heartbeat (`BACKUP_PING_URL` in `.env` makes the script call it on success and at `/fail` on failure; no service chosen yet); the check that the nightly runs prune same-day test copies and keep one copy per day (look on 2026-11-29 with `restic snapshots`); the check in the console that the files are stored in the Multi-AZ class; a failed run (wrong key, no network) was not tried.

## Dates to remember (backup bucket, set up 2026-11-27)

| When | What | Why |
|---|---|---|
| **2027-02-15** (the trial ends about 2027-02-25) | In the Scaleway console look at Billing and the size of the bucket `legalrag-backup-7k3q9x`; find out what happens after the 90-day free trial of Object Storage | The trial gives 750 GB for 90 days from the bucket's creation, then pay as you go (Multi-AZ about 0.016 euro per GB a month, so about a cent for this backup); the end-of-trial behaviour is not written in the contract pages read |
| **2027-10-27** (the key expires about 2027-11-27; the console shows the exact date) | Replace the backup API key: IAM, API keys, generate a new key for the application `legalrag-backup` (preferred project `legalrag-demo`), put it in `.env` on the server and in the local `.env`, run a backup by hand, then delete the old key | Keys of this organisation last 1 year at most; an expired key makes the nightly backup fail (the heartbeat should tell, once it exists) |
| **Any time** | The backup passphrase (`BACKUP_PASSPHRASE`) is also in the owner's password manager. Without it the backups cannot be read, and no one can recover it | It is the only item of the backup that cannot be recovered |

## When the model side fails (tested with fakes, and the 429 with real calls on 2026-11-27)

Every failure keeps the five articles; what differs is the status, the wait and the signal for the operator. The client waits at most 30 s per attempt with one retry (`LLM_TIMEOUT`, `LLM_RETRIES` in `web/build.py`), so a failing call ends before nginx's 120 s; a test keeps it so.

| Failure | Visitor gets | Recorded | Operator action |
|---|---|---|---|
| 429: project rate limit or a token budget (Scaleway answers "You exceeded your current project rate limit", with `x-ratelimit-reset-tokens`, no `Retry-After`) | 503 with `Retry-After` from the header (1 to 60 s), the page's "unavailable" wording | trace error `RateLimitError`; not counted as failing | none for a burst; if it repeats, look at traffic and the limits in the console |
| 401 or 403: key revoked, expired, or its rights removed | 502, articles only | trace error (`AuthenticationError`, `PermissionDeniedError`); after 3 in a row `/health` shows `llm_failing: true` | create a new key, update `.env`, `up -d app` |
| 404: the model name no longer exists | 502, articles only | `NotFoundError`; counts towards `llm_failing` | change `LLM_MODEL` (and its price row) |
| Timeout, connection error, 5xx | 502, articles only (after one retry) | the error class; counts towards `llm_failing` | wait, check Scaleway's status; kill switch if it lasts |
| The reply is not valid JSON or has no valid citation | `parse_error`, `invalid_citation` as before | as before | none |

The uptime check of phase 3 should alert on `"llm_failing": true` in `/health`. **There is no automatic fallback to another provider**: a silent switch to DeepSeek's own API would send visitors' questions to China, against `/privacy`. Switching is a deliberate change of the `LLM_*` lines.

## Checks from outside (phase 2; done on the server on 2026-11-27 from the Mac)

With the proxy private (`HTTP_PORT=127.0.0.1:8080`, the normal state): from the Mac only SSH answers; ports 80, 443, 5432, 8000, 8080 and 3000 do not (`nc -z -w4`), and `ss -ltn` on the server lists only sshd, the local resolvers and the proxy on 127.0.0.1:8080. Docker publishes ports around the firewall, so this had to be tested, not assumed: it holds because the compose file publishes only the proxy and binds it to localhost.

With the proxy opened to the internet for about two minutes (`HTTP_PORT=80`, then set back), tested from the Mac over the real network:

- all pages and static files answer; `/docs` and unknown paths answer 404;
- a plain search, one with a forged `X-Real-IP` and one with a forged `X-Forwarded-For` got the **same visitor code**, and that code differs from the one of the requests made on the server itself: nginx saw the Mac's real address and ignored what the visitor wrote;
- a 20 kB body gets 413, a 20 kB header 400, a request with both `Content-Length` and `Transfer-Encoding` 400, a stalled body is closed after 10 s.

Before the site is public: open it only by setting `HTTP_PORT=80` (and `up -d proxy`) after phases 3 and 4 are done and the user agrees.

## Measured on a Mac (arm64, Docker Desktop, 2026-11-26)

Image 2.49 GB (nginx 92 MB); memory after a few searches: app 1.03 GiB, db 55 MiB, proxy 7.6 MiB; first search 1.1 s, then 0.35 to 0.5 s on a 985-chunk test database.

## Measured on the server (OVHcloud VPS, 4 vCPU, 7.6 GiB, amd64, the full 12,136-chunk database, 2026-11-27)

Image 2.62 GB, built on the server in 154 s. Memory: at rest app 959 MiB, db 43 MiB, proxy 4.6 MiB (about 1.0 GiB of 7.6 GiB); after 6 searches and 5 answers app 994 MiB, db 121 MiB. `/search`: 1.0 s for the first request, then 0.28 to 0.35 s. `/ask` on Scaleway, total time: 3.1, 1.5, 2.3, 2.9 and 1.0 s (five different questions; 3 answered, 2 refused by the model). The top 5 articles and their scores for two test questions are identical to those on the Mac (arm64), so the arm64 and amd64 builds search the same. Start-up to healthy: under 20 s with the weights in the volume. Not measured: a sustained load (the client limit is 5 answers a minute per visitor).

## The server itself (trial, phase 2)

Ubuntu 24.04 on an OVHcloud VPS: SSH with a sudo user (root login off), UFW allowing 22, 80 and 443 only, fail2ban on the `sshd` jail, unattended security updates, Docker from Docker's apt repository. The user chose to keep SSH password login on; the reasoning and the date are in decision D12 of `docs/decisions/0009-deployment-stage-plan.md`. Backups (D7), monitoring and heartbeats (D8) and the privacy text (phase 4) are not done yet.

State on 2026-11-27: the repository is cloned in the home folder of the sudo user, the stack runs with the proxy on the server's localhost only (`127.0.0.1:8080`), so it is not reachable from the internet; from outside, only SSH (port 22) answers, and ports 80, 443, 5432, 8000, 8080 and 3000 do not (checked with `nc` from another machine, and with `ss -ltn` on the server: the only listeners are sshd, the local resolvers and the proxy on 127.0.0.1:8080). To look at the pages from the laptop, use a tunnel: `ssh -L 18080:127.0.0.1:8080 SERVER`, then `http://127.0.0.1:18080/`.
