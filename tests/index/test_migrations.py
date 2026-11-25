"""The migrations form one line: two heads (two migrations written from the same parent) would make `alembic upgrade head`
fail on a deploy. Running them on an empty database is done by every test that uses the `database_name` fixture."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).parents[2]


def script_directory() -> ScriptDirectory:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    return ScriptDirectory.from_config(cfg)


def test_the_migrations_have_one_head_and_one_root():
    scripts = script_directory()
    assert len(scripts.get_heads()) == 1, scripts.get_heads()
    assert len(scripts.get_bases()) == 1, scripts.get_bases()


def test_every_migration_file_is_part_of_the_line():
    scripts = script_directory()
    in_line = {revision.revision for revision in scripts.walk_revisions()}
    files = {p.stem.split("_")[0] for p in (ROOT / "migrations/versions").glob("0*.py")}
    assert len(in_line) == len(files), (sorted(in_line), sorted(files))
