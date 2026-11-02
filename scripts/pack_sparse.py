"""Check the bge-m3 sparse vectors of the default chunking and publish them as one GitHub Release.

Dry run by default: prints the checks, the checksums and the release command. --publish creates the
release (outward-facing: the repository is public). Weights of public law texts only (decision of 2026-10-22).
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from legalrag import embed, variants

FOLDER = Path("data/embeddings")
TAG = "embeddings-bge-m3-sparse-v1"
STEM = "bge-m3-sparse-default"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check() -> dict:
    """The run record; stops when a file is missing or the run is not publishable."""
    for suffix in (".parquet", ".run.json"):
        if not (FOLDER / f"{STEM}{suffix}").exists():
            raise SystemExit(f"missing {FOLDER / (STEM + suffix)}; run `make sparse-embed` first")
    record = json.loads((FOLDER / f"{STEM}.run.json").read_text())
    if record["variant"] != variants.DEFAULT or record["chunk_settings"] != variants.settings(variants.DEFAULT):
        raise SystemExit(f"{STEM}: the run record is not for the default chunking")
    if record.get("model") != embed.MODEL:
        raise SystemExit(f"{STEM}: the run record is for model {record.get('model')!r}, not {embed.MODEL!r}")
    if record.get("limit"):
        raise SystemExit(f"{STEM}: a trial run (--limit {record['limit']}); rerun without --limit")
    if embed.DIRTY in record["git_commit"]:
        raise SystemExit(f"{STEM}: made from a tree with uncommitted changes")
    return record


def notes(record: dict) -> str:
    lines = [
        f"bge-m3 sparse (word weight) vectors for the step 0c keyword comparison (`src/legalrag/sparse.py`): "
        f"{record['rows']} chunks of the default chunking (Code du travail FR, GDPR FR, GDPR EN), one row per chunk "
        "with token ids and weights. "
        f"Produced at commit {record['git_commit'][:7]} on {record.get('gpu') or 'unknown GPU'}, "
        f"model revision {record['model_revision'][:8]}. Settings and counts are in the run.json.",
        "",
        "SHA-256:",
    ]
    lines += [f"{sha256(FOLDER / f'{STEM}{s}')}  {STEM}{s}" for s in (".parquet", ".run.json")]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true", help="create the GitHub Release (default: dry run)")
    args = parser.parse_args()
    record = check()
    body = notes(record)
    files = [str(FOLDER / f"{STEM}{s}") for s in (".parquet", ".run.json")]
    print(body)
    if not args.publish:
        print("dry run; would run: gh release create", TAG, f"({len(files)} files)")
        return
    subprocess.run(["gh", "release", "create", TAG, *files, "--title", "bge-m3 sparse vectors, default chunking",
                    "--notes", body], check=True)


if __name__ == "__main__":
    main()
