"""Query rewriting (step 0c): an LLM restates a lay question in the wording of the code. The search then
runs on the rewrite alone or fused with the original question. The calls are in scripts/rewrite_questions.py.
"""

import json

from legalrag.answering import articlenum

# A rewrite with one of these flags is not used: the original question is searched instead.
UNUSABLE = {"empty", "article_number"}


def messages(prompt: dict, question: str) -> list[dict]:
    return [{"role": "system", "content": prompt["system"].strip()},
            {"role": "user", "content": prompt["user"].format(question=question).strip()}]


def clean(answer: str, max_words: int) -> tuple[str, list[str]]:
    """(rewrite, flags): the first non-empty line without quotes, and what is wrong with it, if anything."""
    lines = [line.strip() for line in answer.strip().splitlines() if line.strip()]
    rewrite = lines[0].strip(" \"'«»").replace("’", "'") if lines else ""  # the gold questions use straight apostrophes
    flags = []
    if not rewrite:
        flags.append("empty")
    if len(lines) > 1:
        flags.append("several_lines")
    if len(rewrite.split()) > max_words:
        flags.append("too_long")
    if articlenum.mentions_article(rewrite):
        flags.append("article_number")
    return rewrite, flags


def used_text(question: str, rewrite: str, flags: list[str]) -> str:
    """The text that is searched: the rewrite, or the question when the rewrite cannot be used."""
    return question if UNUSABLE & set(flags) else rewrite


def load_used(path) -> dict[str, str]:
    """question id -> text to search, from a rewrite file written by scripts/rewrite_questions.py."""
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return {r["id"]: r["used"] for r in rows if r.get("type") != "run"}
