.PHONY: db-up db-down migrate load-chunks load-embeddings db-check fetch embed sanity smoke llm-balance llm-ledger profile verify test lint fresh-rebuild

SOURCE ?= legi

migrate:
	uv run legalrag migrate

load-chunks:
	uv run legalrag load-chunks

load-embeddings:
	uv run legalrag load-embeddings

db-check:
	uv run legalrag db-check

fetch:
	uv run legalrag fetch

embed:
	uv run legalrag embed

sanity:
	uv run legalrag sanity

smoke:
	uv run --extra embed legalrag smoke

llm-balance:
	uv run --env-file .env legalrag llm-balance

llm-ledger:
	uv run legalrag llm-ledger

profile:
	uv run legalrag profile $(SOURCE)

verify:
	uv run legalrag verify $(SOURCE)

db-up:
	docker compose up -d db

db-down:
	docker compose down

fresh-rebuild:
	uv run python scripts/fresh_rebuild.py

test:
	uv run pytest

lint:
	uv run ruff check .
