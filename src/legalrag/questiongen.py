"""Question writing: prompts, parsing and the automatic checks that run before any review."""

import hashlib
import json
import re
import unicodedata
from pathlib import Path

import yaml

PROMPTS = Path("prompts")
ARTICLE_REF = re.compile(r"\b[LRD]\.?\s?\d{3,4}-\d|\barticles?\s+\d+", re.IGNORECASE)
DUPLICATE_OVERLAP = 0.7
MAX_WORDS = 30
# Two questions joined by "et": "..., et combien de temps ?"
COMPOUND = re.compile(
    r"\bet\s+(?:est-ce que|puis-je|peux-je|peut-on|dois-je|doit-il|comment|combien|quand|"
    r"pourquoi|quel|quelle|quels|quelles|où)\b",
    re.IGNORECASE,
)


def load_prompts(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def writer_messages(prompts: dict, style: str, article_body: str) -> list[dict]:
    """The model sees the article body only, never the header, number or code name."""
    return [
        {"role": "system", "content": prompts["base"]},
        {"role": "user", "content": f"{prompts['styles'][style]['text']}\nArticle :\n{article_body}"},
    ]


def reviewer_messages(prompts: dict, style: str, article_body: str, question: dict) -> list[dict]:
    user = (
        f"Style demandé : {style.split('.')[0]}\n\nArticle :\n{article_body}\n\n"
        f"Question : {question['question']}\nRéponse courte : {question['reponse_courte']}"
    )
    return [{"role": "system", "content": prompts["system"]}, {"role": "user", "content": user}]


def prompt_hash(prompts: dict, style: str) -> str:
    text = prompts["base"] + prompts["styles"][style]["text"]
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def parse_json(text: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"not valid JSON: {text[:80]!r}") from error
    if not isinstance(data, dict):
        raise TypeError(f"JSON is not an object: {text[:80]!r}")
    return data


def content_words(text: str) -> set[str]:
    plain = unicodedata.normalize("NFD", text.lower())
    plain = "".join(c for c in plain if unicodedata.category(c) != "Mn")
    return {w for w in re.findall(r"[a-z]+", plain) if len(w) >= 5}


def overlap(question: str, article_body: str) -> float:
    words = content_words(question)
    return len(words & content_words(article_body)) / len(words) if words else 0.0


def automatic_checks(
    question: dict, article_body: str, max_overlap: float | None, earlier: list[str]
) -> list[str]:
    """Flags for the doubtful list; a flagged question is never accepted without a human look."""
    text = str(question.get("question") or "").strip()
    if not text or not str(question.get("reponse_courte") or "").strip():
        return ["missing question or short answer"]
    flags = []
    if text.count("?") > 1 or len(text.split()) > MAX_WORDS:
        flags.append("several questions or too long")
    if COMPOUND.search(text):
        flags.append("compound question (two ideas)")
    if ARTICLE_REF.search(text):
        flags.append("cites an article number")
    if max_overlap is not None and overlap(text, article_body) > max_overlap:
        flags.append(f"copies the article wording (overlap above {max_overlap})")
    words = content_words(text)
    for other in earlier:
        shared = words & content_words(other)
        if words and len(shared) / len(words | content_words(other)) >= DUPLICATE_OVERLAP:
            flags.append("near duplicate of an earlier question")
            break
    return flags
