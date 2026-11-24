import contextlib
import subprocess

import pytest
from typer.testing import CliRunner

from legalrag import cli
from legalrag.answering import cache as answer_cache
from legalrag.answering import trace as answer_trace
from legalrag.cli import index as index_cli
from legalrag.index import db, embed, store

runner = CliRunner()


def test_the_service_starts_without_the_web_server_access_log(monkeypatch):
    """The access log of uvicorn prints the visitor's raw address; the privacy notice says that it is not kept."""
    uvicorn = pytest.importorskip("uvicorn")
    started = {}
    monkeypatch.setattr(uvicorn, "run", lambda *args, **kwargs: started.update(kwargs))
    assert runner.invoke(cli.app, ["serve"]).exit_code == 0
    assert started["access_log"] is False and started["workers"] == 1
    assert started["h11_max_incomplete_event_size"] == 16 * 1024 and started["timeout_keep_alive"] == 5


def git(path, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=path, check=True, capture_output=True,
    )


@pytest.fixture
def repo(tmp_path, monkeypatch):
    git(tmp_path, "init", "-q")
    (tmp_path / "a.txt").write_text("one")
    git(tmp_path, "add", "a.txt")
    git(tmp_path, "commit", "-q", "-m", "first")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_git_commit_flags_only_a_dirty_tree(repo):
    clean = embed.git_commit()
    assert len(clean) == 40 and not clean.endswith(embed.DIRTY)
    (repo / "a.txt").write_text("two")
    assert embed.git_commit() == clean + embed.DIRTY


def test_load_chunks_refuses_a_dirty_tree_before_touching_data(monkeypatch):
    monkeypatch.setattr(embed, "git_commit", lambda: "abc" + embed.DIRTY)
    monkeypatch.setattr(index_cli, "token_counter", lambda _: pytest.fail("ran past the check"))
    result = runner.invoke(cli.app, ["load-chunks"])
    assert result.exit_code == 1
    assert "Uncommitted changes" in result.output


def test_allow_dirty_goes_past_the_check(monkeypatch):
    monkeypatch.setattr(embed, "git_commit", lambda: "abc" + embed.DIRTY)

    def stop(_):
        raise RuntimeError("past the check")

    monkeypatch.setattr(index_cli, "token_counter", stop)
    result = runner.invoke(cli.app, ["load-chunks", "--allow-dirty"])
    assert isinstance(result.exception, RuntimeError)


@pytest.fixture
def deleted(monkeypatch):
    """Stub the database: run 'r' has 5 chunks and 5 vectors; returns the names passed to delete_run."""
    calls = []
    monkeypatch.setattr(db, "connect", lambda: contextlib.nullcontext(object()))
    monkeypatch.setattr(store, "run_size", lambda _, name: (5, 5) if name == "r" else None)
    monkeypatch.setattr(store, "delete_run", lambda _, name: calls.append(name))
    return calls


def test_delete_run_shows_the_size_and_waits_for_confirmation(deleted):
    refused = runner.invoke(cli.app, ["delete-run", "r"], input="n\n")
    assert "5 chunks and 5 vectors" in refused.output
    assert refused.exit_code != 0 and deleted == []
    assert runner.invoke(cli.app, ["delete-run", "r"], input="y\n").exit_code == 0
    assert deleted == ["r"]


def test_delete_run_yes_skips_the_question_and_an_unknown_run_is_refused(deleted):
    assert runner.invoke(cli.app, ["delete-run", "r", "--yes"]).exit_code == 0
    assert runner.invoke(cli.app, ["delete-run", "nope", "--yes"]).exit_code != 0
    assert deleted == ["r"]


@pytest.fixture
def cache_calls(monkeypatch):
    """Stub the database and the cache: 3 valid and 2 expired entries; returns the names of the calls."""
    calls = []
    monkeypatch.setattr(db, "connect", lambda: contextlib.nullcontext(object()))
    monkeypatch.setattr(answer_cache, "counts", lambda _: (3, 2))
    monkeypatch.setattr(answer_cache, "clear", lambda _: calls.append("clear") or 5)
    monkeypatch.setattr(answer_cache, "purge", lambda _: calls.append("purge") or 2)
    return calls


def test_maintain_erases_deletes_and_purges_in_one_command_without_asking(monkeypatch):
    calls = []
    monkeypatch.setattr(db, "connect", lambda: contextlib.nullcontext(object()))
    monkeypatch.setattr(answer_trace, "scrub", lambda _: calls.append("scrub") or 4)
    monkeypatch.setattr(answer_trace, "purge", lambda _: calls.append("purge") or 3)
    monkeypatch.setattr(answer_cache, "purge", lambda _: calls.append("cache") or 2)
    result = runner.invoke(cli.app, ["maintain"])
    assert result.exit_code == 0 and calls == ["scrub", "purge", "cache"]  # the text is erased before the rows are deleted
    assert "4 requests erased, 3 traces deleted, 2 expired cache entries deleted" in result.output


def test_cache_clear_shows_the_counts_and_waits_for_confirmation(cache_calls):
    refused = runner.invoke(cli.app, ["cache", "clear"], input="n\n")
    assert "3 valid and 2 expired" in refused.output and refused.exit_code != 0 and cache_calls == []
    assert runner.invoke(cli.app, ["cache", "clear", "--yes"]).exit_code == 0 and cache_calls == ["clear"]


def test_cache_purge_removes_the_expired_entries_without_asking(cache_calls):
    result = runner.invoke(cli.app, ["cache", "purge"])
    assert result.exit_code == 0 and "2 expired entries deleted, 3 valid ones kept" in result.output and cache_calls == ["purge"]
