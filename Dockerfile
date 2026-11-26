# The web service (step 0f): code, prompts and migrations only. The bge-m3 weights (about 2.2 GB) are not in the image:
# they live in a volume mounted at /models and are loaded offline (see docs/decisions/0009-deployment-stage-plan.md).

FROM python:3.12-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /usr/local/bin/uv
# embed-cpu: torch from the CPU index; the default extra `embed` would pull the CUDA build (see pyproject.toml).
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project --extra serve --extra embed-cpu
COPY src ./src
RUN uv sync --locked --no-dev --extra serve --extra embed-cpu

FROM python:3.12-slim-bookworm
RUN useradd --system --uid 10001 --no-create-home app && mkdir /models && chown app /models
WORKDIR /app
# The code finds prompts/, migrations/ and alembic.ini relative to the repo root (index/db.py: ROOT), so the layout stays.
COPY --from=build /app /app
COPY prompts ./prompts
COPY migrations ./migrations
COPY alembic.ini ./
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 HF_HOME=/models HF_HUB_OFFLINE=1
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
# Behind the proxy only: the compose file publishes no port of this service.
CMD ["legalrag", "serve", "--host", "0.0.0.0", "--port", "8000"]
