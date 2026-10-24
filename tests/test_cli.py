import subprocess

import pytest
from typer.testing import CliRunner

from legalrag import cli, embed

runner = CliRunner()


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
    monkeypatch.setattr(cli, "token_counter", lambda _: pytest.fail("ran past the check"))
    result = runner.invoke(cli.app, ["load-chunks"])
    assert result.exit_code == 1
    assert "Uncommitted changes" in result.output


def test_allow_dirty_goes_past_the_check(monkeypatch):
    monkeypatch.setattr(embed, "git_commit", lambda: "abc" + embed.DIRTY)

    def stop(_):
        raise RuntimeError("past the check")

    monkeypatch.setattr(cli, "token_counter", stop)
    result = runner.invoke(cli.app, ["load-chunks", "--allow-dirty"])
    assert isinstance(result.exception, RuntimeError)
