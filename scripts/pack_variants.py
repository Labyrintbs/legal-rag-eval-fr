"""Check the embeddings of the chunking variants and publish them as one GitHub Release.

Dry run by default: prints the checks, the checksums and the release command. --publish creates the
release (outward-facing: the repository is public). Vectors of public law texts only (decision of
2026-10-22); never use this for BSARD or any other licensed data.
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from legalrag import embed, variants

TAG = "embeddings-bge-m3-variants-v1"
FOLDER = Path("data/embeddings")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(names: list[str]) -> dict[str, dict]:
    """The run record of every variant; stops when a file is missing or the runs do not fit together."""
    records = {}
    for name in names:
        stem = variants.embeddings_name(name)
        for suffix in (".parquet", ".run.json"):
            if not (FOLDER / f"{stem}{suffix}").exists():
                raise SystemExit(f"missing {FOLDER / (stem + suffix)}; run `make embed-variants` first")
        record = json.loads((FOLDER / f"{stem}.run.json").read_text())
        if record["variant"] != name or record["chunk_settings"] != variants.settings(name):
            raise SystemExit(f"{stem}: the run record does not match variant {name!r}")
        if record.get("limit"):
            raise SystemExit(f"{stem}: a trial run (--limit {record['limit']}); rerun without --limit")
        if embed.DIRTY in record["git_commit"]:
            raise SystemExit(f"{stem}: made from a tree with uncommitted changes")
        records[name] = record
    commits = {r["git_commit"] for r in records.values()}
    revisions = {r["model_revision"] for r in records.values()}
    if len(commits) > 1 or len(revisions) > 1:
        raise SystemExit(f"runs differ in commit {sorted(commits)} or model revision {sorted(revisions)}")
    return records


def notes(records: dict[str, dict]) -> str:
    first = next(iter(records.values()))
    lines = [
        "Dense bge-m3 vectors (1,024 dims, normalised) of the chunking variants compared in step 0c "
        "(`src/legalrag/variants.py`): Code du travail FR, GDPR FR, GDPR EN. "
        f"Produced at commit {first['git_commit'][:7]} on {first.get('gpu', 'unknown GPU')}, "
        f"model revision {first['model_revision'][:8]}. Settings and counts are in each run.json.",
        "",
        "| variant | chunks | file |",
        "|---|---|---|",
    ]
    lines += [f"| {n} | {r['rows']} | {variants.embeddings_name(n)}.parquet |" for n, r in records.items()]
    lines += ["", "SHA-256:"]
    for name in records:
        for suffix in (".parquet", ".run.json"):
            path = FOLDER / f"{variants.embeddings_name(name)}{suffix}"
            lines.append(f"{sha256(path)}  {path.name}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true", help="create the GitHub Release (default: dry run)")
    args = parser.parse_args()

    names = [n for n in variants.VARIANTS if n != variants.DEFAULT]
    records = check(names)
    body = notes(records)
    files = [str(FOLDER / f"{variants.embeddings_name(n)}{s}") for n in names for s in (".parquet", ".run.json")]
    print(body)
    command = ["gh", "release", "create", TAG, *files, "--title", "bge-m3 embeddings, chunking variants",
               "--notes", body]
    if not args.publish:
        print("dry run; would run: gh release create", TAG, f"({len(files)} files)")
        return
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
