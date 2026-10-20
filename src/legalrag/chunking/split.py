import re
from collections.abc import Callable

# Words after which a full stop does not end a sentence ("art. 5", "n° 2006-340" is handled by the
# lowercase check). Single capital letters cover "L. 8113-6", "R. 4312-1", "D. 1234-5".
ABBREVIATIONS = {"art", "al", "arts", "no", "nos", "p", "pp", "etc", "cf", "ex", "s", "ss"}
_BOUNDARY = re.compile(r"[.!?]\s+(?=[A-ZÀ-ÝŒ0-9])")


def split_sentences(text: str) -> list[str]:
    pieces, start = [], 0
    for m in _BOUNDARY.finditer(text):
        word = text[start : m.start()].rsplit(" ", 1)[-1]
        if (len(word) == 1 and word.isupper()) or word.lower() in ABBREVIATIONS:
            continue
        pieces.append(text[start : m.start() + 1])
        start = m.end()
    pieces.append(text[start:])
    return pieces


def split_paragraphs(text: str) -> list[str]:
    return [p for p in text.split("\n") if p.strip()]


def pack(
    pieces: list[str],
    budget: int,
    count_tokens: Callable[[str], int],
    sep: str = " ",
) -> list[tuple[str, bool]]:
    """Greedily join consecutive pieces so each group fits the budget (tokens, header excluded).

    Returns (text, forced) pairs; forced is True when a single piece alone exceeded the budget and
    was cut into word windows.
    """
    groups: list[tuple[str, bool]] = []
    current: list[str] = []
    used = 0
    for piece in pieces:
        cost = count_tokens(piece) + 1
        if cost > budget:
            if current:
                groups.append((sep.join(current), False))
                current, used = [], 0
            groups.extend((w, True) for w in _word_windows(piece, budget, count_tokens))
            continue
        if used + cost > budget and current:
            groups.append((sep.join(current), False))
            current, used = [], 0
        current.append(piece)
        used += cost
    if current:
        groups.append((sep.join(current), False))
    return groups


def _word_windows(text: str, budget: int, count_tokens: Callable[[str], int]) -> list[str]:
    windows, current, used = [], [], 0
    for word in text.split(" "):
        cost = count_tokens(word) + 1
        if used + cost > budget and current:
            windows.append(" ".join(current))
            current, used = [], 0
        current.append(word)
        used += cost
    if current:
        windows.append(" ".join(current))
    return windows
