from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from pgvector.psycopg import register_vector

from legalrag.index.config import database_url

ROOT = Path(__file__).resolve().parents[3]


def connect(url: str | None = None) -> psycopg.Connection:
    """Connection that adapts numpy arrays to the vector type (the schema must exist)."""
    conn = psycopg.connect(url or database_url())
    register_vector(conn)
    return conn


def migrate(url: str | None = None) -> None:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    if url:
        cfg.attributes["url"] = url
    command.upgrade(cfg, "head")
