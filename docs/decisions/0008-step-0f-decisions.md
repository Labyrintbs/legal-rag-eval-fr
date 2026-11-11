# Step 0f decisions: web service and demo page

Background and the list of what 0f contains: `docs/decisions/0005-web-service-and-demo.md`. Decisions are taken one at a time, in this order: 1 framework and process layout, 2 API contract, 3 client identity, 4 caching, 5 feedback box, 6 article-number rule, 7 demo page, 8 memory and speed on the target server.

| # | Decision | Who, when |
|---|---|---|
| 1 | FastAPI with one worker process; bge-m3 is loaded inside it at start; at most 2 questions are embedded at the same time (semaphore). Not chosen: Flask/Gunicorn (no Pydantic link), a separate embedding service (two things to deploy, a network hop), Streamlit/Gradio (0005). Measured on the Mac CPU (8 cores, 12 French dev questions): bge-m3 takes about 1.0 GB loaded and peaks at 1.95 GB after queries; embedding one question takes a median of 156 ms (max 201 ms). The 2.5 GB of 0005 was a guess. The target server is not measured yet (decision 8) | User, 2026-11-11 |
