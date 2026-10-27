"""Question writing: prompts, parsing and the automatic checks that run before any review."""

import hashlib
import json
import re
import unicodedata
from pathlib import Path

import yaml

from legalrag import llm

PROMPTS = Path("prompts")
ARTICLE_REF = re.compile(r"\b[LRD]\.?\s?\d{3,4}-\d|\barticles?\s+\d+", re.IGNORECASE)
DUPLICATE_OVERLAP = 0.7
CONTEXT_LEVELS = 4
# Above the 30 words the prompt asks for: 33-word questions were fine in the audit.
MAX_WORDS = 35
# Two questions joined by "et": "..., et combien de temps ?", "... et est-il payé ?"
COMPOUND = re.compile(
    r"\bet\s+(?:est-ce que|puis-je|peux-je|peut-on|dois-je|doit-il|comment|combien|quand|"
    r"pourquoi|quel|quelle|quels|quelles|où|(?:est|sont|a|ont|peut|doit|faut)-(?:il|elle|ils|elles|on))\b",
    re.IGNORECASE,
)


def load_prompts(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def context_of(section_path: str, levels: int = CONTEXT_LEVELS) -> str:
    """The last section levels, which name the scope of an article (a contract, a risk, a category)."""
    return " > ".join(level[:120] for level in section_path.split(" > ")[-levels:])


def writer_messages(prompts: dict, style: str, article_body: str, context: str = "") -> list[dict]:
    """The model sees the article body, and the section context for the styles that ask for it;
    never the article number or the code name."""
    entry = prompts["styles"][style]
    scope = f"Contexte : {context}\n" if entry.get("context") else ""
    return [
        {"role": "system", "content": prompts["base"]},
        {"role": "user", "content": f"{entry['text']}\n{scope}Article :\n{article_body}"},
    ]


def reviewer_messages(
    prompts: dict, reviewer: str, style: str, article_body: str, context: str, question: dict
) -> list[dict]:
    entry = prompts["reviewers"][reviewer]
    scope = f"Contexte : {context}\n\n" if entry["context"] else ""
    user = (
        f"Style demandé : {style.split('.')[0]}\n\n{scope}Article :\n{article_body}\n\n"
        f"Question : {question['question']}\nRéponse courte : {question['reponse_courte']}"
    )
    return [{"role": "system", "content": entry["system"]}, {"role": "user", "content": user}]


def prompt_hash(prompts: dict, style: str) -> str:
    entry = prompts["styles"][style]
    text = prompts["base"] + entry["text"] + ("+context" if entry.get("context") else "")
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def parse_json(text: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"not valid JSON: {text[:80]!r}") from error
    if not isinstance(data, dict):
        raise TypeError(f"JSON is not an object: {text[:80]!r}")
    return data


def run_call(
    http, budget: llm.Budget, label: str, model: str, messages: list[dict], max_tokens: int,
    temperature: float | None = None, thinking: bool = False, reasoning_effort: str | None = None,
):
    """(answer, None), or (None, error) when the answer is empty or not a JSON object; a budget
    stop still raises, and an empty answer is still in the ledger."""
    try:
        text = llm.chat(
            http, llm.LEDGER, budget, label, model, messages, max_tokens, thinking=thinking,
            temperature=temperature, reasoning_effort=reasoning_effort,
        )
        return parse_json(text), None
    except (ValueError, TypeError, KeyError) as error:
        return None, str(error)


def review_problems(review: dict | None, checks: dict) -> list[str]:
    """The reviewer's failed or missing checks; its overall verdict alone is not trusted."""
    if not review or "error" in review:
        return ["review failed"]
    problems = [] if review.get("verdict") == "accept" else [f"verdict {review.get('verdict')}"]
    for field, passing in checks.items():
        if field not in review:
            problems.append(f"missing {field}")
        elif review[field] != passing:
            problems.append(field)
    return problems


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
