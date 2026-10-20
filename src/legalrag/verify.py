import random
from collections import defaultdict
from collections.abc import Callable

import numpy as np

from legalrag.models import Article, Chunk
from legalrag.text import normalize_text

EXPECTED_LEGI_ARTICLES = 11_433
# Body token percentiles recorded in docs/data_profiles/code_travail.md and gdpr.md.
EXPECTED_LEGI_BODY_PCT = {50: 95, 90: 268, 95: 376, 99: 736}
EXPECTED_GDPR_FR_BODY_PCT = {50: 345, 90: 1160, 95: 1262, 99: 1725}
EXPECTED_GDPR_EN_BODY_PCT = {50: 276, 90: 913, 95: 1034, 99: 1298}

Check = tuple[str, bool, str]


def _check(name: str, bad: list) -> Check:
    return (name, not bad, f"{len(bad)} failing {bad[:3]}" if bad else "")


def _common(
    articles: list[Article],
    chunks: list[Chunk],
    count_tokens: Callable[[str], int],
    max_tokens: int,
    expected_pct: dict[int, int],
) -> list[Check]:
    by_article: dict[str, list[Chunk]] = defaultdict(list)
    for c in chunks:
        by_article[c.article_uid].append(c)
    seen: set[str] = set()
    dup_ids = [a.native_id for a in articles if a.native_id in seen or seen.add(a.native_id)]
    tokens = [count_tokens(a.body_text) for a in articles if a.kind != "recital"]
    pct = {p: int(np.percentile(tokens, p)) for p in expected_pct}
    rejoin_bad = [
        a.native_id
        for a in articles
        if normalize_text(" ".join(c.body_text for c in by_article[a.uid]))
        != normalize_text(a.body_text)
    ]
    return [
        _check("native id unique", dup_ids),
        _check("no empty body", [a.native_id for a in articles if not a.body_text]),
        _check("every article has chunks", [a.uid for a in articles if not by_article[a.uid]]),
        _check(
            "every chunk has header and body",
            [c.article_uid for c in chunks if not c.header_text or not c.body_text],
        ),
        _check(
            f"every chunk <= {max_tokens} tokens",
            [c.article_uid for c in chunks if c.token_count > max_tokens],
        ),
        _check("split pieces rejoin to the original body", rejoin_bad),
        _check(
            "header contains the article number",
            [
                c.article_uid
                for a in articles
                for c in by_article[a.uid]
                if a.article_num not in c.header_text
            ],
        ),
        _check(
            "section_path round trip",
            [
                a.native_id
                for a in articles
                if " > ".join(a.section_path.split(" > ")) != a.section_path
            ],
        ),
        ("body token percentiles match profile", pct == expected_pct, f"got {pct}"),
    ]


def verify_legi(
    articles: list[Article],
    chunks: list[Chunk],
    count_tokens: Callable[[str], int],
    max_tokens: int = 1024,
) -> list[Check]:
    return [
        (
            f"{EXPECTED_LEGI_ARTICLES} articles",
            len(articles) == EXPECTED_LEGI_ARTICLES,
            f"got {len(articles)}",
        ),
        *_common(articles, chunks, count_tokens, max_tokens, EXPECTED_LEGI_BODY_PCT),
    ]


def verify_gdpr(
    articles: dict[str, list[Article]],
    chunks: dict[str, list[Chunk]],
    count_tokens: Callable[[str], int],
    max_tokens: int = 1024,
) -> list[Check]:
    """`articles` and `chunks` are keyed by language ("fr", "en")."""
    expected = {"fr": EXPECTED_GDPR_FR_BODY_PCT, "en": EXPECTED_GDPR_EN_BODY_PCT}
    out: list[Check] = []
    for lang, arts in articles.items():
        only = [a for a in arts if a.kind == "article"]
        rct = [a for a in arts if a.kind == "recital"]
        chapters = {a.section_path.split(" > ")[0] for a in only}
        sections = {a.section_path for a in only if " > " in a.section_path}
        out += [
            (f"[{lang}] 99 articles, 173 recitals", (len(only), len(rct)) == (99, 173),
             f"got {len(only)}, {len(rct)}"),
            (f"[{lang}] 11 chapters, 15 sections", (len(chapters), len(sections)) == (11, 15),
             f"got {len(chapters)}, {len(sections)}"),
            (f"[{lang}] article numbers 1..99 contiguous",
             sorted(int(a.article_num) for a in only) == list(range(1, 100)), ""),
            _check(f"[{lang}] every article has a title", [a.uid for a in only if not a.title]),
        ]
        out += [
            (f"[{lang}] {name}", ok, detail)
            for name, ok, detail in _common(arts, chunks[lang], count_tokens, max_tokens,
                                            expected[lang])
        ]
    fr_ids = {a.native_id for a in articles["fr"]}
    en_ids = {a.native_id for a in articles["en"]}
    out.append(("FR and EN have the same ids", fr_ids == en_ids, ""))
    a5 = next(a for a in articles["fr"] if a.native_id == "art_5")
    paragraphs = a5.body_text.split("\n\n")
    points = [line[:2] for line in paragraphs[0].split("\n")[1:]]
    out.append((
        "Article 5 (fr): paragraph 1 has points a) to f), then paragraph 2",
        len(paragraphs) == 2 and points == [f"{c})" for c in "abcdef"]
        and paragraphs[1].startswith("2. Le responsable du traitement"),
        f"points {points}",
    ))
    return out


def spot_check_sample(articles: list[Article], n: int = 20, seed: int = 0) -> list[Article]:
    return random.Random(seed).sample(articles, n)
