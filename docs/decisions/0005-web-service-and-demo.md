# Decision: a web service and a demo page (step 0f)

Decided with the user on 2026-11-02. The master plan (outside the repository) had a live demo in its goal and in stage 3, and the guardrails for a public demo, but no step that builds the service or the page. Step 0f is added after 0e (quality gate) and before the Oracle and Hetzner stages, so there is something to deploy.

## What 0f contains
- An HTTP API on the retrieval code the evaluation uses: `POST /ask` (answer with cited articles, or a refusal), `POST /search` (retrieved articles and passages only), `GET /health`.
- One demo page served by the API itself (plain HTML and JavaScript): a question box with example questions; the answer with its cited articles linked to the source text, or a clear refusal; a search-only toggle that shows the retrieved passages; a "how it is measured" panel with the dev and test numbers and the method; the disclaimer "legal information, not legal advice".
- The guardrails of 0d on every public route: per-client limits and a daily cost cap (decisions 13 to 15 of 0006, `limits.py`), answer caching, the kill switch (a flag in the database, `legalrag service llm-off`; search only), no raw IPs in the trace.
- A feedback box under every answer (requested by the user, 2026-11-09), for an HR visitor or any web user: a thumbs up or down, and a free-text comment that can be an error report or advice. The backend exists: `trace.set_feedback` stores a value and a comment on the request's `query_traces` row (30-day expiry). To decide when 0f starts: whether the visitor picks a kind (wrong answer, wrong citation, missing article, suggestion), the comment length limit, and that a comment may hold personal data, so it is shown to nobody but the owner. Comments about errors feed the review of failures (`legalrag traces export`).

## Options for the page
| Option | For | Against |
|---|---|---|
| 1. One page served by the API (chosen) | one container, nothing else to deploy, no cross-origin setup | plain front end, little polish |
| 2. A separate static page on a free host calling the API | looks like a normal web app, free hosting | a second thing to deploy, cross-origin settings |
| 3. Streamlit or Gradio | quickest to write | heavier, uses memory of the 8 GB server, looks less like a service |

## Dependencies and order
- A search-only first version needs no LLM and costs nothing per query, so it can ship before the answers of 0d exist. The full `/ask` needs 0d.
- The server embeds each query with bge-m3 on its CPU. The memory (about 2.5 GB, unverified) counts toward the stage 0 exit check (under about 6 GB): measure it early, before choosing the server size.
- The approximate-index recall check of `db-check` (84.9% on 2026-11-02) was a setting, not a broken index: the check now sets `hnsw.ef_search` to 100 like `smoke.py` and measures 99.8%. A service that uses the index must set it too (the index holds every chunking run, so the run filter leaves few candidates at the default 40); the evaluation and the answer path use the exact scan.

## Open (to decide when 0f starts)
Page language (French only or with an English toggle), a domain name, whether the measurements panel shows the full tables or a summary, how long traces are kept (the plan says 30 days), and whether the demo is open or behind a simple link.
