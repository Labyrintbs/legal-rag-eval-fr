import hashlib
import re
import unicodedata

_SPACES = re.compile(r"\s+")


def normalize_text(s: str) -> str:
    """Drop invisible format marks (zero-width, bidi), collapse all whitespace to single spaces."""
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Cf")
    return _SPACES.sub(" ", s).strip()


def content_hash(s: str) -> str:
    return hashlib.sha256(normalize_text(s).encode("utf-8")).hexdigest()
