"""Choosing the articles that get model-written questions: weighted by the ministry sheets, or random."""

import random
from collections import Counter

CODE_DU_TRAVAIL = "LEGITEXT000006072050"


def sheet_counts(sheets: list[dict]) -> Counter:
    """How many sheets cite each Code du travail article, once per sheet."""
    counts: Counter = Counter()
    for sheet in sheets:
        cited = {
            article["fmt"]
            for section in sheet["sections"]
            for article in section.get("references", {}).get(CODE_DU_TRAVAIL, {}).get("articles", [])
        }
        counts.update(cited)
    return counts


def part_of(article_num: str) -> str:
    """The part of the code: the first digit of L1237-1, R4412-1, D3141-1."""
    return article_num[1]


def draw(
    rng: random.Random, weights: dict[str, float], k: int, taken_parts: Counter, max_per_part: int
) -> list[str]:
    """Weighted draw without replacement. A part already at the cap is skipped; taken_parts is
    shared between calls so the cap holds across the weighted and the random draw."""
    pool = dict(weights)
    chosen = []
    while len(chosen) < k:
        eligible = sorted(a for a in pool if taken_parts[part_of(a)] < max_per_part)
        if not eligible:
            break
        article = rng.choices(eligible, weights=[pool[a] for a in eligible])[0]
        chosen.append(article)
        taken_parts[part_of(article)] += 1
        del pool[article]
    return chosen
