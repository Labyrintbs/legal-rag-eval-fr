"""Checks on the repository itself: nothing that must stay out of a public repo is tracked, and the documents agree with
the code (the code map lists every module, the README names only `make` targets that exist)."""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
FORBIDDEN_SUFFIXES = {".parquet", ".npy", ".npz", ".pt", ".pth", ".safetensors", ".bin", ".db", ".sqlite", ".sqlite3",
                      ".zip", ".tar", ".gz", ".pkl", ".pem", ".key"}
MAX_BYTES = 1_000_000


def tracked() -> list[Path]:
    result = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        pytest.skip("not a git checkout")
    return [ROOT / name for name in result.stdout.split("\0") if name and (ROOT / name).is_file()]


def test_no_data_secret_or_large_file_is_tracked():
    """The repo is public: raw data, embeddings and secrets stay out (gitleaks only finds secrets in the text)."""
    problems = []
    for path in tracked():
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith("data/") or path.name == ".env" or path.suffix in FORBIDDEN_SUFFIXES:
            problems.append(f"{relative}: a kind of file that stays out of the repo")
        elif path.stat().st_size > MAX_BYTES:
            problems.append(f"{relative}: {path.stat().st_size} bytes, more than {MAX_BYTES}")
    assert not problems, "\n".join(problems)


def test_the_code_map_lists_every_module():
    text = (ROOT / "docs/CODE_MAP.md").read_text()
    names = [p.stem for p in (ROOT / "src/legalrag").rglob("*.py") if p.stem != "__init__"]
    missing = sorted(name for name in names if f"`{name}`" not in text)
    assert not missing, f"modules missing from docs/CODE_MAP.md: {missing}"


def test_the_readme_names_only_make_targets_that_exist():
    targets = set(re.findall(r"^([a-z][\w-]*):", (ROOT / "Makefile").read_text(), re.MULTILINE))
    named = set(re.findall(r"\bmake ([a-z][\w-]*)", (ROOT / "README.md").read_text()))
    assert named <= targets, f"not in the Makefile: {sorted(named - targets)}"


def test_the_local_links_of_the_readme_and_the_code_map_lead_to_a_file():
    broken = []
    for document in ("README.md", "docs/CODE_MAP.md"):
        base = (ROOT / document).parent
        for target in re.findall(r"\]\(([^)#\s]+)", (ROOT / document).read_text()):
            if not target.startswith(("http://", "https://", "mailto:")) and not (base / target).exists():
                broken.append(f"{document}: {target}")
    assert not broken, "\n".join(broken)
