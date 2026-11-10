"""Article-number rule: a question that names an article ("Que dit l'article L1221-13 ?") gets that
article first, found by its number; the first search fills the places below it.
"""

import re

import psycopg

from legalrag.corpus.labels import article_label

CODE_NUMBER = re.compile(r"(?<![\w*-])([LRD]\*?\d{4}(?:-\d+)+)(?![\w-])")
GDPR_ARTICLE = re.compile(r"\b(?:article|art\.?)\s+(\d{1,3})\b", re.IGNORECASE)
GDPR_RECITAL = re.compile(r"\b(?:considérant|recital)\s+(\d{1,3})\b", re.IGNORECASE)
GDPR_NAME = re.compile(r"\b(?:RGPD|GDPR)\b", re.IGNORECASE)
MENTION = re.compile(r"\b[LRD]\.?\s?\d{3,4}-\d|\barticles?\s+\d+", re.IGNORECASE)
NAMED_ARTICLES = (
    "SELECT source_code, kind, article_num, content_hash FROM articles "
    "WHERE lang = CASE WHEN source_code = 'code_travail' THEN 'fr' ELSE %s END "
    "AND source_code || '|' || kind || '|' || article_num = ANY(%s)"
)


def mentions_article(text: str) -> bool:
    """True when the text names an article by number, in any of the ways a model might write it."""
    return bool(MENTION.search(text) or CODE_NUMBER.search(text))


def named_articles(question: str) -> list[tuple[str, str, str]]:
    """(source_code, kind, article_num) of every article the question names, in the order of the text.
    Bare numbers ("article 17") count only when the question names the GDPR, since the Code du travail
    numbers always carry a letter."""
    found = [("code_travail", "article", m.group(1)) for m in CODE_NUMBER.finditer(question)]
    if GDPR_NAME.search(question):
        found += [("rgpd", "article", m.group(1)) for m in GDPR_ARTICLE.finditer(question)]
    found += [("rgpd", "recital", m.group(1)) for m in GDPR_RECITAL.finditer(question)]
    return list(dict.fromkeys(found))


def lookup(conn: psycopg.Connection, question: str, lang: str) -> list[tuple[str, str]]:
    """(label, content hash) of the named articles that exist; GDPR articles in the question's language,
    the Code du travail only exists in French."""
    named = named_articles(question)
    if not named:
        return []
    rows = conn.execute(NAMED_ARTICLES, (lang, ["|".join(n) for n in named])).fetchall()
    stored = {(source, kind, num): body_hash for source, kind, num, body_hash in rows}
    return [(article_label(*n), stored[n]) for n in named if n in stored]


def put_first(named: list[tuple[str, str]], ranking: list[tuple[str, str]], keep: int) -> list[tuple[str, str]]:
    """The named articles, then the ranking without them, cut to `keep`."""
    labels = {label for label, _ in named}
    return (named + [item for item in ranking if item[0] not in labels])[:keep]
