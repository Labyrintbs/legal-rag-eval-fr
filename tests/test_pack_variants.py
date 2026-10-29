import importlib.util
import json
from pathlib import Path

import pytest

from legalrag import variants

spec = importlib.util.spec_from_file_location("pack_variants", Path(__file__).parents[1] / "scripts" / "pack_variants.py")
pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)

NAMES = [n for n in variants.VARIANTS if n != variants.DEFAULT]


def write_run(folder: Path, name: str, **changes) -> None:
    record = {"variant": name, "chunk_settings": variants.settings(name), "git_commit": "a" * 40,
              "model_revision": "r" * 40, "limit": None, "rows": 12000, "gpu": "test", "model": "BAAI/bge-m3"} | changes
    stem = variants.embeddings_name(name)
    (folder / f"{stem}.parquet").write_bytes(b"vectors")
    (folder / f"{stem}.run.json").write_text(json.dumps(record))


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(pack, "FOLDER", tmp_path)
    for name in NAMES:
        write_run(tmp_path, name)
    return tmp_path


def test_complete_runs_pass_and_are_listed_in_the_notes(folder):
    records = pack.check(NAMES)
    body = pack.notes(records)
    assert all(f"| {n} | 12000 |" in body for n in NAMES)
    assert body.count("bge-m3-") >= 2 * len(NAMES)


def test_missing_file_stops_the_pack(folder):
    (folder / "bge-m3-size-512.parquet").unlink()
    with pytest.raises(SystemExit, match="missing"):
        pack.check(NAMES)


def test_trial_run_and_dirty_tree_are_refused(folder):
    write_run(folder, "header-none", limit=40)
    with pytest.raises(SystemExit, match="trial"):
        pack.check(NAMES)
    write_run(folder, "header-none", git_commit="a" * 40 + " (uncommitted changes)")
    with pytest.raises(SystemExit, match="uncommitted"):
        pack.check(NAMES)


def test_runs_from_different_commits_are_refused(folder):
    write_run(folder, "header-full", git_commit="b" * 40)
    with pytest.raises(SystemExit, match="differ"):
        pack.check(NAMES)


def test_record_for_another_variant_is_refused(folder):
    write_run(folder, "header-full", variant="header-none")
    with pytest.raises(SystemExit, match="does not match"):
        pack.check(NAMES)


def test_a_run_record_of_another_model_is_refused(folder):
    write_run(folder, "header-full", model_key="qwen3-embedding-0.6b")
    with pytest.raises(SystemExit, match="not 'bge-m3'"):
        pack.check(NAMES)


def test_other_models_are_packed_on_the_default_chunking_only(tmp_path, monkeypatch):
    monkeypatch.setattr(pack, "FOLDER", tmp_path)
    key = "qwen3-embedding-0.6b"
    record = {"variant": variants.DEFAULT, "chunk_settings": variants.settings(variants.DEFAULT), "git_commit": "a" * 40,
              "model_revision": "r" * 40, "limit": None, "rows": 12136, "model": "Qwen/Qwen3-Embedding-0.6B",
              "model_key": key}
    (tmp_path / f"{key}-main.parquet").write_bytes(b"vectors")
    (tmp_path / f"{key}-main.run.json").write_text(json.dumps(record))
    records = pack.check([variants.DEFAULT], key)
    body = pack.notes(records, key)
    assert "Qwen/Qwen3-Embedding-0.6B vectors" in body and f"{key}-main.parquet" in body
