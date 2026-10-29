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

FOLDER = Path("data/embeddings")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(names: list[str], model: str = embed.BASELINE_KEY) -> dict[str, dict]:
    """The run record of every variant; stops when a file is missing or the runs do not fit together."""
    records = {}
    for name in names:
        stem = variants.embeddings_name(name, model)
        for suffix in (".parquet", ".run.json"):
            if not (FOLDER / f"{stem}{suffix}").exists():
                raise SystemExit(f"missing {FOLDER / (stem + suffix)}; run `make embed-variants` first")
        record = json.loads((FOLDER / f"{stem}.run.json").read_text())
        if record["variant"] != name or record["chunk_settings"] != variants.settings(name):
            raise SystemExit(f"{stem}: the run record does not match variant {name!r}")
        if record.get("model_key", embed.BASELINE_KEY) != model:
            raise SystemExit(f"{stem}: the run record is for model {record.get('model_key')!r}, not {model!r}")
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


def notes(records: dict[str, dict], model: str = embed.BASELINE_KEY) -> str:
    first = next(iter(records.values()))
    lines = [
        f"Dense {first['model']} vectors (1,024 dims, normalised) for the step 0c comparisons "
        "(`src/legalrag/variants.py`): Code du travail FR, GDPR FR, GDPR EN. "
        f"Produced at commit {first['git_commit'][:7]} on {first.get('gpu', 'unknown GPU')}, "
        f"model revision {first['model_revision'][:8]}. Settings and counts are in each run.json.",
        "",
        "| variant | chunks | file |",
        "|---|---|---|",
    ]
    lines += [f"| {n} | {r['rows']} | {variants.embeddings_name(n, model)}.parquet |" for n, r in records.items()]
    lines += ["", "SHA-256:"]
    for name in records:
        for suffix in (".parquet", ".run.json"):
            path = FOLDER / f"{variants.embeddings_name(name, model)}{suffix}"
            lines.append(f"{sha256(path)}  {path.name}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=embed.BASELINE_KEY, choices=list(embed.EMBEDDING_MODELS))
    parser.add_argument("--publish", action="store_true", help="create the GitHub Release (default: dry run)")
    args = parser.parse_args()

    # the baseline model is compared across chunking variants; other models only on the default chunking
    baseline = args.model == embed.BASELINE_KEY
    names = [n for n in variants.VARIANTS if n != variants.DEFAULT] if baseline else [variants.DEFAULT]
    tag = "embeddings-bge-m3-variants-v1" if baseline else f"embeddings-{args.model}-v1"
    title = "bge-m3 embeddings, chunking variants" if baseline else f"{args.model} embeddings, default chunking"
    records = check(names, args.model)
    body = notes(records, args.model)
    files = [str(FOLDER / f"{variants.embeddings_name(n, args.model)}{s}")
             for n in names for s in (".parquet", ".run.json")]
    print(body)
    command = ["gh", "release", "create", tag, *files, "--title", title, "--notes", body]
    if not args.publish:
        print("dry run; would run: gh release create", tag, f"({len(files)} files)")
        return
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
