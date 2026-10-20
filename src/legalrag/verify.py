import random
from collections import defaultdict
from collections.abc import Callable

import numpy as np

from legalrag.models import Article, Chunk
from legalrag.text import normalize_text

EXPECTED_LEGI_ARTICLES = 11_433
# Body token percentiles recorded in docs/data_profiles/code_travail.md.
EXPECTED_LEGI_BODY_PCT = {50: 95, 90: 268, 95: 376, 99: 736}

Check = tuple[str, bool, str]


def verify_legi(
    articles: list[Article],
    chunks: list[Chunk],
    count_tokens: Callable[[str], int],
    max_tokens: int = 1024,
) -> list[Check]:
    by_article: dict[str, list[Chunk]] = defaultdict(list)
    for c in chunks:
        by_article[c.article_uid].append(c)

    def check(name: str, bad: list) -> Check:
        return (name, not bad, f"{len(bad)} failing {bad[:3]}" if bad else "")

    seen: set[str] = set()
    dup_ids = [a.native_id for a in articles if a.native_id in seen or seen.add(a.native_id)]
    pct = {p: int(np.percentile([count_tokens(a.body_text) for a in articles], p))
           for p in EXPECTED_LEGI_BODY_PCT}
    rejoin_bad = [
        a.native_id
        for a in articles
        if normalize_text(" ".join(c.body_text for c in by_article[a.uid])) != a.body_text
    ]
    return [
        (
            f"{EXPECTED_LEGI_ARTICLES} articles",
            len(articles) == EXPECTED_LEGI_ARTICLES,
            f"got {len(articles)}",
        ),
        check("article_id unique", dup_ids),
        check("no empty body", [a.native_id for a in articles if not a.body_text]),
        check("every article has chunks", [a.uid for a in articles if not by_article[a.uid]]),
        check(
            "every chunk has header and body",
            [c.article_uid for c in chunks if not c.header_text or not c.body_text],
        ),
        check(
            f"every chunk <= {max_tokens} tokens",
            [c.article_uid for c in chunks if c.token_count > max_tokens],
        ),
        check("split pieces rejoin to the original body", rejoin_bad),
        check(
            "header contains the article number",
            [c.article_uid for a in articles for c in by_article[a.uid]
             if a.article_num not in c.header_text],
        ),
        check(
            "section_path round trip",
            [a.native_id for a in articles if " > ".join(a.section_path.split(" > ")) != a.section_path],
        ),
        (
            "body token percentiles match profile",
            pct == EXPECTED_LEGI_BODY_PCT,
            f"got {pct}",
        ),
    ]


def spot_check_sample(articles: list[Article], n: int = 20, seed: int = 0) -> list[Article]:
    return random.Random(seed).sample(articles, n)
