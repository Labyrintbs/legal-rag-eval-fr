# Decision: a web service and a demo page (step 0f)

Decided with the user on 2026-11-02. The master plan (outside the repository) had a live demo in its goal and in stage 3, and the guardrails for a public demo, but no step that builds the service or the page. Step 0f is added after 0e (quality gate) and before the Oracle and Hetzner stages, so there is something to deploy.

## What 0f contains
- An HTTP API on the retrieval code the evaluation uses: `POST /ask` (answer with cited articles, or a refusal), `POST /search` (retrieved articles and passages only), `GET /health`.
- One demo page served by the API itself (plain HTML and JavaScript): a question box with example questions; the answer with its cited articles linked to the source text, or a clear refusal; a search-only toggle that shows the retrieved passages; a "how it is measured" panel with the dev and test numbers and the method; the disclaimer "legal information, not legal advice".
- The guardrails of 0d on every public route: per-IP limit, daily question cap, answer caching, the kill switch `LLM_ENABLED=false` (search only), no raw IPs in the trace.

## Options for the page
| Option | For | Against |
|---|---|---|
| 1. One page served by the API (chosen) | one container, nothing else to deploy, no cross-origin setup | plain front end, little polish |
| 2. A separate static page on a free host calling the API | looks like a normal web app, free hosting | a second thing to deploy, cross-origin settings |
| 3. Streamlit or Gradio | quickest to write | heavier, uses memory of the 8 GB server, looks less like a service |

## Dependencies and order
- A search-only first version needs no LLM and costs nothing per query, so it can ship before the answers of 0d exist. The full `/ask` needs 0d.
- The server embeds each query with bge-m3 on its CPU. The memory (about 2.5 GB, unverified) counts toward the stage 0 exit check (under about 6 GB): measure it early, before choosing the server size.
- The approximate-index recall check of `db-check` (84.9% on 2026-11-02, 98% wanted) must be fixed before the service uses the vector index; the evaluation uses the exact scan.

## Open (to decide when 0f starts)
Page language (French only or with an English toggle), a domain name, whether the measurements panel shows the full tables or a summary, how long traces are kept (the plan says 30 days), and whether the demo is open or behind a simple link.
