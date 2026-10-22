.PHONY: db-up db-down fetch embed sanity profile verify test lint

SOURCE ?= legi

fetch:
	uv run legalrag fetch

embed:
	uv run legalrag embed

sanity:
	uv run legalrag sanity

profile:
	uv run legalrag profile $(SOURCE)

verify:
	uv run legalrag verify $(SOURCE)

db-up:
	docker compose up -d db

db-down:
	docker compose down

test:
	uv run pytest

lint:
	uv run ruff check .
