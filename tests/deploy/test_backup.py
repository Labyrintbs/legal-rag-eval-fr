import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
SCRIPT = (ROOT / "deploy/backup.sh").read_text()

# Tables that hold visitors' questions or answers to them: never copied to the backup (/privacy keeps them 7 to 30 days).
PERSONAL = {"query_traces", "answer_cache"}


def migration_tables() -> set[str]:
    text = "\n".join(p.read_text() for p in (ROOT / "migrations/versions").glob("*.py"))
    return set(re.findall(r"CREATE TABLE (?:IF NOT EXISTS )?([a-z_]+)", text))


def backed_up() -> set[str]:
    return set(re.search(r'^TABLES="([^"]+)"', SCRIPT, re.MULTILINE).group(1).split())


def test_no_table_with_visitors_text_is_backed_up():
    assert not backed_up() & PERSONAL


def test_every_table_is_either_backed_up_or_named_personal():
    unclassified = migration_tables() - backed_up() - PERSONAL
    assert not unclassified, f"decide for {sorted(unclassified)}: add to TABLES in deploy/backup.sh or to PERSONAL here"


def test_the_backup_lists_only_tables_that_exist():
    assert backed_up() - {"alembic_version"} <= migration_tables()
