"""Download the raw source files into data/raw and check their SHA-256."""

import hashlib
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

USER_AGENT = "Mozilla/5.0 (research)"  # the Publications Office endpoint rejects the default agent


class ChecksumError(Exception):
    pass


@dataclass(frozen=True)
class RawFile:
    name: str
    url: str
    sha256: str
    headers: dict[str, str] = field(default_factory=dict)


_GDPR_URL = "https://publications.europa.eu/resource/celex/32016R0679"

SOURCES: dict[str, list[RawFile]] = {
    "legi": [
        RawFile(
            "legi_vincegx33_train.parquet",
            "https://huggingface.co/datasets/VinceGx33/legi-french-law-2025/resolve/"
            "refs%2Fconvert%2Fparquet/default/train/0000.parquet",
            "6b4e2fde6daab5fa92bccec533037a33e27f4df353b4f7e647cc356f3018287b",
        )
    ],
    "gdpr": [
        RawFile(
            "gdpr_fr.xhtml",
            _GDPR_URL,
            "27a2248cf0cf7c79a3ec7eae30b6e871817230d9f577632fed915181642144c2",
            {"Accept": "application/xhtml+xml", "Accept-Language": "fr"},
        ),
        RawFile(
            "gdpr_en.xhtml",
            _GDPR_URL,
            "962539af03738bf552319ff4ce42d69e5f95a576307c4dfed7bf87e81b646b9d",
            {"Accept": "application/xhtml+xml", "Accept-Language": "en"},
        ),
    ],
    "tokenizer": [
        RawFile(
            "bge-m3-tokenizer.json",
            "https://huggingface.co/BAAI/bge-m3/resolve/main/tokenizer.json",
            "21106b6d7dab2952c1d496fb21d5dc9db75c28ed361a05f5020bbba27810dd08",
        )
    ],
}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch_file(f: RawFile, dest: Path) -> str:
    """Return "present" (already there with the right checksum) or "downloaded"."""
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / f.name
    if target.exists() and sha256_of(target) == f.sha256:
        return "present"
    part = target.with_name(target.name + ".part")
    req = urllib.request.Request(f.url, headers={"User-Agent": USER_AGENT, **f.headers})
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=60) as resp, part.open("wb") as out:
        for block in iter(lambda: resp.read(1 << 20), b""):
            h.update(block)
            out.write(block)
    if h.hexdigest() != f.sha256:
        # Keep the file for inspection; an upstream change must not be accepted silently.
        mismatch = target.with_name(target.name + ".mismatch")
        part.replace(mismatch)
        raise ChecksumError(f"{f.name}: expected {f.sha256}, got {h.hexdigest()} (kept {mismatch})")
    part.replace(target)
    return "downloaded"
