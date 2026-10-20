.PHONY: db-up db-down profile verify test lint

profile:
	uv run legalrag profile

verify:
	uv run legalrag verify

db-up:
	docker compose up -d db

db-down:
	docker compose down

test:
	uv run pytest

lint:
	uv run ruff check .
