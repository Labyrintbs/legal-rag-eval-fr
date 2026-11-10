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


def context_of(section_path: str, levels: int = 4) -> str:
    """The last section levels, which name the scope of an article (a contract, a risk, a category)."""
    return " > ".join(level[:120] for level in section_path.split(" > ")[-levels:])
