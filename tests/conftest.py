"""Fixtures shared by the tests that need a database."""

import uuid
from urllib.parse import urlparse

import psycopg
import pytest

from legalrag import db
from legalrag.config import database_url


def with_database(url: str, name: str) -> str:
    return urlparse(url)._replace(path="/" + name).geturl()


@pytest.fixture(scope="module")
def database_name():
    """A throwaway database on the dev server; the tests skip when no server is reachable."""
    try:
        admin = psycopg.connect(with_database(database_url(), "postgres"), autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("no Postgres reachable at DATABASE_URL (run `make db-up`)")
    name = f"legalrag_test_{uuid.uuid4().hex[:8]}"
    admin.execute(f"CREATE DATABASE {name}")
    try:
        db.migrate(with_database(database_url(), name))
        yield name
    finally:  # also when the migration fails, so no throwaway database is left behind
        admin.execute(f"DROP DATABASE {name} WITH (FORCE)")
        admin.close()


@pytest.fixture
def conn(database_name):
    c = db.connect(with_database(database_url(), database_name))
    yield c
    c.rollback()  # each test leaves the database as it found it
    c.close()


