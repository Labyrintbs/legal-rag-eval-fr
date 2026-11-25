"""Fixtures shared by the tests that need a database, and the rule that in CI a skipped test is a failure."""

import os
import uuid
from urllib.parse import urlparse

import psycopg
import pytest

from legalrag.index import db
from legalrag.index.config import database_url


def pytest_sessionfinish(session, exitstatus):
    """CI has every dependency, the database and the fixtures: a skip there means a test silently stopped running
    (a missing package, a file not downloaded). Skips stay allowed on a development machine."""
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    skipped = reporter.stats.get("skipped", []) if reporter else []
    if os.environ.get("CI") and skipped and session.exitstatus == 0:
        reporter.write_line(f"{len(skipped)} test(s) skipped in CI, which counts as a failure; see -rs", red=True)
        session.exitstatus = 1


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


