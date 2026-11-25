# Deployment stage plan (draft for review, 2026-11-25)

Status: a plan, nothing decided. Each decision below is taken one at a time, in this order, with the user. Built from the master plan (outside the repo: D11 Hetzner, D12 AWS, later stages 1 to 6, standing rules), the open points of `0008-step-0f-decisions.md`, the deployment reminders, and web sources read on 2026-11-25 (links at the end). A claim from a web page is marked **(web)**; a claim from memory or an estimate is marked **(unverified)**; a fact about this repo is marked **(repo)**.

## 1. Goal and what "done" means

A public demo, reachable at a stable HTTPS address, that HR readers and recruiters can use; cost bounded; visitors' data handled as `/privacy` says; recoverable by one person in under an hour. Done means all of:

1. The demo answers real questions from a server that is not the Mac, at an address on the CV.
2. The retention table of `/privacy` is true (the hourly `maintain` job runs and is watched).
3. A backup was restored on a clean machine and the answers matched (drill done, dated).
4. The kill switch was used from outside, on purpose, and brought back.
5. Two weeks without a manual fix, the bill checked once, no surprise.

## 2. Where we start (repo)

- One process (FastAPI, uvicorn, 1 worker) with bge-m3 loaded inside; about 1.0 GB loaded, 1.95 GB peak on the Mac CPU, 156 ms to embed a question (decision 1 of 0008). Postgres 16 with pgvector; the dev database holds 8 chunking runs, production needs only `default`.
- **There is no Dockerfile.** `docker-compose.yml` runs only the database for development (repo).
- `pyproject.toml` pulls the **CUDA 12.6 torch wheel on Linux** (repo). On a CPU-only server that would put several GB of GPU libraries in the image; the image needs the CPU wheel.
- The model provider is fixed in code: `llm.BASE_URL = https://api.deepseek.com`, model `deepseek-flash`, and a DeepSeek-specific request field that switches thinking off (repo: `llm.py`, `web/build.py`). Another provider means a small code change and a new measurement.
- Settings come from environment variables: `DEEPSEEK_API_KEY`, `TRACE_SECRET`, `DATABASE_URL`, `CLIENT_IP_HEADER`, `CODE_VERSION`, `DATA_VERSION`, `CACHE_WARM_FILE`, `EMBED_DEVICE` (repo).
- Already built: per-client limits, daily cap ($0.10), kill switch, answer cache with pinned examples, personal-data filter, 7-day erasure and 30-day deletion (`legalrag maintain`), `/health`, security headers, one visitor request at a time.
- Not measured on a server: memory, speed, the limits under real traffic (decision 8 of 0008).

## 3. What the evidence changes in the old draft

| Old draft | What the sources say | Effect |
|---|---|---|
| D11: Hetzner CX33, EUR 8.49 + 0.50 IPv4, hourly trial | Hetzner's status page has carried "limited availability of cloud instances" since 26 June 2026, and checks in September and October 2026 show the cost-optimized CX plans as unavailable **(web: bitdoze, Better Stack)**. The June list price of CX33 is EUR 8.49 **(web)**, the dedicated-vCPU CPX line rose far more (CPX22 about EUR 19.99 **(web)**). | Do not assume Hetzner. Check live availability on the day; have OVHcloud as the planned alternative (decision D1). |
| D11: OVHcloud VPS-2 EUR 9.99 | OVHcloud lists a 4 vCore / 8 GB VPS from $8.50 on its US page and the 2 vCore / 4 GB VPS-1 at EUR 3.81 ex VAT on its Irish page **(web)**; a blog reports a mid-June 2026 increase **(web, unverified)**. | Price must be read in the OVH configurator with a European datacentre. |
| Reminder 1: "an EU-hosted DeepSeek at other prices" | DeepSeek's own policy says data is stored in China, and regulators in Italy, Ireland, Belgium, the Netherlands, France and Berlin asked about transfers **(web)**. Scaleway Generative APIs (hosted in Europe) lists `deepseek-v4-flash-0731` at EUR 0.40 input, 0.08 cached, 0.80 output per million tokens **(web)**; DeepSeek's own price is about $0.14 / $0.0028 / $0.28 **(web)**. | The EU route is real and costs roughly 3 times as much per token (decision D2). |
| Stage 2 "backup drill" with 7 daily + 4 weekly dumps | Backups keep text longer than `/privacy` allows if they contain `query_traces` (7 days for ordinary text, 30 days for the kept ones). | Decide what is backed up (D7); do not copy the traces table to long-lived backups. |
| "Docker Compose + Caddy" | Confirmed as a common, documented pattern (full-stack-fastapi-template, several 2026 guides) **(web)**. A published container port bypasses UFW rules **(web: Docker docs, several posts)**. | Keep as is; publish only Caddy's 80 and 443, never the database or the app (D4, D12). |

## 4. Decisions, in dependency order

Each has options, a recommendation and why. None is taken yet.

### D1. The server
| Option | For | Against |
|---|---|---|
| A. Hetzner CX33 (4 vCPU, 8 GB, 80 GB) | cheapest in the old plan (EUR 8.49 + 0.50 IPv4 ex VAT **(web)**), hourly billing for the trial, EU datacentres | reported unavailable for new orders since mid-2026 **(web)**; may not be orderable |
| B. OVHcloud VPS-2 (4 vCore, 8 GB) | French company, French datacentres, daily backup option, similar price **(web: from $8.50 on the US page; EUR price to read)** | monthly billing only (no hourly trial); price rise reported **(unverified)** |
| C. A smaller server (4 GB), after measuring | roughly half the price (OVH VPS-1 EUR 3.81 ex VAT **(web)**) | bge-m3 peak 1.95 GB plus Postgres plus the OS is tight; the Mac figures are not the server's |
| D. Keep the demo on the Mac behind a tunnel | free | not a deployment; the demo is down when the Mac sleeps |

Recommendation: **on the decision day, check A and B live; take A if it can be ordered, else B, both at 4 vCPU / 8 GB**, then measure memory in the trial and consider C only with the numbers. Scaleway and other French hosts were not searched; add them only if A and B both fail **(unverified)**.

### D2. The model provider (also a privacy decision)
| Option | For | Against |
|---|---|---|
| A. DeepSeek direct | cheapest (about $0.14 / $0.28 per million tokens **(web)**), the model we measured | data stored in China per its policy, regulator investigations **(web)**; the transfers sentence of `/privacy` would have to say so |
| B. DeepSeek V4 Flash on an EU host (Scaleway lists it, EUR 0.40 / 0.08 / 0.80 **(web)**) | same model family, data stays in Europe | about 3 times the price; a different model version than the one measured; code change for base URL and model name |
| C. An EU-native model (for example Mistral Small on Scaleway, EUR 0.15 / 0.35 **(web)**) | EU company, cheapest EU option | a different model: the whole answer evaluation and the prompts are re-measured |
| D. Self-host a model | no transfer at all | needs a GPU server: far over budget |

Recommendation: **B**, because the privacy answer is simple and the model family is the one we measured. Work it needs: make base URL and model name settings (and the thinking field a setting), re-run the dev answer measures (faithfulness, answer relevancy, the gate replay) on the new endpoint before the switch, and re-check the price on the day. A measured answer cost $0.0004 on DeepSeek direct; at the Scaleway price it is about $0.001 **(estimate)**, so the $0.10 daily cap is about 100 answers; the cap is a decision for the trial (D10).

### D3. Packaging
- A `Dockerfile` for the app (Python 3.12, `uv sync --locked`, **CPU torch wheel**, non-root user) and a production `compose.yaml` with three services: `app`, `db` (pgvector 0.8.7-pg16, data in a named volume, no published port), `caddy` (80 and 443, certificate volume). App and db on an internal network; only Caddy touches the outside **(web: pattern in several guides)**.
- bge-m3 weights (about 2.2 GB) are not in git. Options: bake them into the image (slow builds, big image) or download once into a volume with a checksum, as `legalrag fetch` does for other files. Recommendation: **volume, downloaded once**, so a code deploy does not move 2 GB.
- Images are tagged with the commit SHA (and `CODE_VERSION` is set to it, so the cache key changes with each deploy).

### D4. The reverse proxy and the visitor address
- Caddy terminates HTTPS (automatic certificates **(web)**) and passes the request to `app:8000`. In Caddy, only listed upstream peers are believed for forwarded headers (`trusted_proxies`), and forum reports show header settings that fail silently **(web)**. Recommendation: Caddy sets one header (`X-Real-IP` or `X-Forwarded-For` from its own view of the connection), the app reads it through `CLIENT_IP_HEADER` and trusts only the proxy's address (`--forwarded-allow-ips`), and **a test from outside proves that a forged header changes nothing** (the red team of 0f found this is not covered by the app alone).
- Proxy limits to add (from the red-team list): body cap 16 kB, body read timeout, header size limits, refusal of ambiguous requests; Caddy access logs off or with a short retention, since they hold raw addresses.

### D5. Data on the server
Rebuild from the Release assets (`migrate`, `load-chunks`, `load-embeddings` of the `default` run only, `db-check`, then the gate floors on the server) rather than copy a dump: it is the reproducible path and `fresh-rebuild` already tests it. The corpus snapshot date stays on `/data`.

### D6. Deploy and rollback
Options: (a) a script run by hand over SSH (`docker compose pull && up -d`, wait for `/health`, previous tag kept); (b) the same steps in a GitHub Actions job triggered by a tag. Rollback is a deploy of the previous SHA tag, about ten seconds **(web)**. Recommendation: **(a) for the trial and the first weeks, (b) once the steps are stable**; `up -d` swaps containers with a few seconds of downtime, accepted (no uptime promise in the master plan). The warm-up of the 10 example questions runs at start (about $0.004).

### D7. Backups
- What matters: the corpus and vectors are rebuildable from Releases; the answer cache is rebuildable; traces and feedback are the only live data, and they are personal data with a retention limit. A backup that keeps them longer than the `/privacy` table is a breach of our own text.
- Options: (a) nightly `pg_dump` of everything to an encrypted off-site copy; (b) the same but **excluding `query_traces`** (feedback comments and votes stay in it, so decide whether they are worth keeping); (c) no backup of data, only of the configuration, because everything else is rebuildable.
- Recommendation: **(c) plus a nightly encrypted dump of the configuration and the non-personal tables**, with `restic` to an S3-compatible bucket (encryption is the default **(web)**) and a restore drill on a scratch machine; install the pgvector extension before restoring **(web: EDB docs)**. A logical dump gives no point-in-time recovery **(web)**; with data this low in value that is accepted and written down.

### D8. Scheduled jobs and monitoring
- `legalrag maintain` every hour (cron or a systemd timer on the host calling `docker compose exec`), and the nightly backup.
- A heartbeat after each job (Healthchecks.io free tier: 20 checks, alerts when a ping is missing **(web)**) and an uptime check on `/health` (Better Stack's free plan includes commercial use; UptimeRobot's free plan is non-commercial **(web)**). Alerts to the user's e-mail.
- Until the hourly job is proven, the `/privacy` retention table is not true: a gate item (phase 3).

### D9. Legal and privacy pages
- Name the host on `/privacy`, replace the transfers sentence according to D2, keep the retention table in line with the code and the schedule, check the "no cookie" claim against CNIL guidance.
- A half-page record of processing (GDPR art. 30). The CNIL publishes a basic register template in ODS format for small structures **(web)**; whether a hobby portfolio must keep one is read differently by sites **(web, unverified)**, and the half page is cheap. The host or the model provider is a processor: read its standard data processing agreement and keep a copy (art. 28) **(web, unverified)**.
- French site notices (publisher and host identification) for a public site: not searched; check on CNIL and service-public pages before launch **(unverified)**.

### D10. Money guardrails
Provider spend cap or balance alert set before the first public visit; the daily cap of the service re-set after D2; a monthly look at the host and provider bills; the limits (5 a minute and 30 a day answers, 30 a minute cached, 5 translations, 10 votes, 30 searches) reviewed after one week of real traffic. OWASP's unbounded-consumption guidance lists per-source limits, input size limits, capped queues and monitoring **(web)**; all are in the service already, the monitoring is the new part.

### D11. Domain and address
A domain (about EUR 12 a year in the master plan **(unverified)**) or a free subdomain. Recommendation: a cheap domain: it is on the CV, and a host or provider change then needs no new link. The contact address stays built on click.

### D12. Hardening checklist (done on the trial server, kept in `OPERATIONS.md`)
SSH keys only and no root login; firewall allowing 22, 80, 443 only **and checked from outside**, because Docker publishes ports around UFW **(web)**; automatic security updates; no secret in an image or in git (environment file, mode 600); containers as non-root; database never published; time synchronised; `gitleaks` stays in CI. Fail2ban is optional once keys are the only way in.

### D13. The `main` branch and pull requests
Agreed 2026-11-25: protection of `main` (pull request and passing CI before merge, no force-push) is switched on at the start of phase 2, when `main` becomes what ships. From then on every change, including mine, goes through a pull request.

### D14. Left for later (unchanged from the master plan)
AWS proof with Terraform (stage 4, account created just before), agent and MCP (optional), freshness (optional), the live question set (needs real traffic; see the memory plan). Oracle Always Free test: skipped; it is arm64 and not the demo host **(master plan: optional)**.

## 5. Phases and review gates

Each phase ends with a review gate; the next does not start before the user approves.

| Phase | Content | Cost | Gate: what the user sees |
|---|---|---|---|
| 0. Decisions | D1, D2, D7, D9, D11 decided one at a time; live prices and availability read; provider choice measured (see D2) | $0 to about $2 (dev answer measures, estimate) | the written decisions, the measured answers on the chosen model |
| 1. Make it deployable | Dockerfile (CPU torch), production compose, Caddyfile, settings for provider and model, `OPERATIONS.md` skeleton; everything tested locally with the compose file | $0 | the app running from the compose file on the Mac, the image size, the test suite green |
| 2. Trial server | Branch protection on; a server by the hour or month; hardening; data load; memory and speed measured (decision 8 of 0008); proxy tests from outside (forged address, big body, slow body); deploy script and rollback tried | a few EUR | the measured numbers, the hardening checklist ticked, the outside tests |
| 3. Operations | `maintain` scheduled, backups and the restore drill, heartbeats and uptime alerts, kill switch used from outside, spend caps set | small | the drill record (dated), an alert received on purpose |
| 4. Privacy and legal | `/privacy` host and transfers sentence, record of processing, retention table checked against a live trace row | $0 | the final text of `/privacy` for the user's reading |
| 5. Soft launch | Domain and HTTPS; the link given to a few people; one week of real traffic; limits and cache hit rate reviewed; first real questions to the review queue | the running cost | the traffic numbers, the bill, any complaint; decision to announce |
| 6. Production | Two stable weeks, link on the CV and in the README, screenshots in the README | the running cost | exit criteria of section 1 |

## 6. Budget (estimates; prices change, re-read on the day)

| Item | Figure | Status |
|---|---|---|
| Server, 4 vCPU / 8 GB | about EUR 9 to 10 a month ex VAT (Hetzner EUR 8.49 + 0.50 IPv4; OVH from $8.50) | web, partly unverified |
| Trial by the hour (Hetzner only) | a few cents a day | master plan |
| Domain | about EUR 12 a year | master plan, unverified |
| Backup storage | small (configuration and light tables) | unpriced |
| Model | about $0.001 per answer on the EU route; the daily cap bounds it | estimate |
| Monitoring | free tiers | web |

## 7. Risks

- No orderable server on the day (D1): the second provider is chosen in advance.
- The EU model behaves differently from the measured one (D2): measured before the switch; if worse, option A with an honest transfers sentence or option C.
- Memory too small: measured in phase 2 before the month is paid.
- A forged address header gives a visitor unlimited quota: tested from outside in phase 2.
- Backups outliving the retention promise (D7): decided before any backup runs.
- A job stops silently (`maintain`, backups): heartbeats.
- Dependabot and a green CI do not test the real model or the real server: a short manual check list before each deploy.

## 8. What I need from the user at each step

Phase 0: pick the server (after I read live availability), the provider route, the backup choice and the domain; confirm who the processor documents are filed under. Later phases: approve each gate. Anything that spends money (the trial server, the domain, a dev answer run on a new endpoint) is asked first.

## Sources (read 2026-11-25; third-party blogs and forum threads are not official documentation)
- Hetzner price adjustment: https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/ ; availability and price guides: https://www.bitdoze.com/hetzner-cloud-cost-optimized-plans/ , https://betterstack.com/community/guides/web-servers/hetzner-cloud-review/
- OVHcloud VPS: https://www.ovhcloud.com/en/vps/ ; price context: https://us.ovhcloud.com/resources/blog/cloud-infrastructure-pricing-in-2026/
- Scaleway Generative APIs: https://www.scaleway.com/en/generative-apis/ , https://www.scaleway.com/en/pricing/model-as-a-service
- DeepSeek pricing: https://api-docs.deepseek.com/quick_start/pricing ; privacy policy: https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html ; regulators: https://iapp.org/news/a/deepseek-and-the-china-data-question-direct-collection-open-source-and-the-limits-of-extraterritorial-enforcement
- EU-hosted inference comparison: https://dev.to/valeria_bernhardt_c9473b7/choosing-an-eu-hosted-inference-provider-a-2026-comparison-5d5h
- FastAPI, Caddy and Compose on a VPS: https://raw.githubusercontent.com/fastapi/full-stack-fastapi-template/master/deployment-docker-compose.md , https://www.github.com/GrantBirki/caddy-fastapi
- Caddy reverse proxy and trusted proxies: https://caddyserver.com/docs/caddyfile/directives/reverse_proxy , https://caddy.community/t/confused-about-the-use-of-trusted-proxies/27516
- Docker published ports and UFW: https://docs.docker.com/network/packet-filtering-firewalls/ , https://github.com/sschoen/ufw-docker
- Backups with pgvector and restic: https://www.enterprisedb.com/docs/pg_extensions/pgvector/operations/ , https://dev.to/overnighthost/how-to-set-up-automated-off-site-backups-for-your-vps-with-restic-506l
- Deploy by SSH and rollback by image tag: https://docs.servicestack.net/ssh-docker-compose-deploment , https://dev.to/lfariaus/from-git-pull-to-gitops-how-i-built-a-production-cicd-pipeline-on-a-12-digitalocean-droplet-34gn
- Monitoring: https://betterstack.com/community/comparisons/uptime-robot-alternatives
- OWASP unbounded consumption: https://genai.owasp.org/llmrisk/llm102025-unbounded-consumption/
- CNIL register of processing: https://www.cnil.fr/fr/RGPD-le-registre-des-activites-de-traitement , https://www.cnil.fr/sites/default/files/atoms/files/registre_rgpd_basique.pdf
