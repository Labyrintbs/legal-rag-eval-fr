import os

# Matches docker-compose.yml and .env.example; real deployments set DATABASE_URL.
DEFAULT_DATABASE_URL = "postgresql://legalrag:legalrag@localhost:5432/legalrag"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
