"""Citable units of a text (step 0d). A chunk is split into units: sentences, numbered list items (1°, 2°...)
and, in the GDPR, points (a), (b). A unit is a slice of the text, so what is shown to the reader is the stored
text. A list item has a lead-in: the unit that introduces the list, shown with it.
"""

import re
from dataclasses import dataclass
from itertools import pairwise

from legalrag.chunking.split import split_sentences

# "3° " when it can be a list item; references such as "le 3° de l'article" are filtered by the run rule.
_ITEM = re.compile(r"(?<![\w°])(\d{1,2})°(\s+(?:bis|ter|quater|quinquies|sexies))?(?=\s)")
_POINT = re.compile(r"^\(?[a-z]{1,3}\)\s")  # a GDPR point at the start of a line: "a) ...;"
GAP = " […] "


@dataclass(frozen=True)
class Unit:
    start: int
    end: int
    lead: int | None = None  # index of the unit that introduces this one, if any


_PARAGRAPH_NUMBER = re.compile(r"\d{1,2}\.")  # "1." opening a GDPR paragraph is not a sentence


def _sentences(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """(start, end) offsets in the whole text of the sentences of text[start:end], without edge spaces."""
    spans, position, pending = [], start, None
    for piece in split_sentences(text[start:end]):
        found = text.find(piece, position)
        if not piece.strip() or found == -1:
            continue
        position = found + len(piece)
        first = found + len(piece) - len(piece.lstrip())
        last = found + len(piece.rstrip())
        if pending is not None:
            first, pending = pending, None
        if _PARAGRAPH_NUMBER.fullmatch(text[first:last]):
            pending = first
            continue
        spans.append((first, last))
    return spans


def _introduced(text: str, start: int, first: int) -> bool:
    """A list opens a line or follows a colon; "aux 1° et 2° de l'article..." is a reference, not a list."""
    before = text[start:first].rstrip()
    return before == "" or before.endswith(":")


def _numbered_run(text: str, start: int, end: int) -> list[int]:
    """Offsets of the items 1°, 2°, 3°... of the first list inside text[start:end] (empty if there is none)."""
    runs, current, expected = [], [], 1
    for m in _ITEM.finditer(text, start, end):
        number = int(m.group(1))
        if m.group(2) and number == expected - 1:  # "1° bis" follows "1°" and is a further item
            current.append(m.start())
        elif number == expected:
            current.append(m.start())
            expected += 1
        elif number == 1:
            runs.append(current)
            current, expected = [m.start()], 2
    runs.append(current)
    return next((run for run in runs if len(run) >= 2 and _introduced(text, start, run[0])), [])


def _line_units(text: str, start: int, end: int) -> list[tuple[int, int, bool]]:
    """(start, end, is_item) of the units of one line; list items come after their lead-in."""
    run = _numbered_run(text, start, end)
    if not run:
        return [(s, e, False) for s, e in _sentences(text, start, end)]
    units = [(s, e, False) for s, e in _sentences(text, start, run[0])]
    units += [(here, len(text[:nxt].rstrip()), True) for here, nxt in pairwise(run)]
    last_end = _sentences(text, run[-1], end)[0][1]  # the last item stops at the end of its sentence
    units.append((run[-1], last_end, True))
    return units + [(s, e, False) for s, e in _sentences(text, last_end, end)]


def split_units(text: str) -> list[Unit]:
    """The units of a text, in order. Lines are split first (GDPR points are lines), then lists and sentences."""
    units: list[Unit] = []
    offset = 0
    for paragraph in text.split("\n\n"):
        lead = None  # the last unit of the paragraph that is not a point or an item
        for line in paragraph.split("\n"):
            start = text.find(line, offset)
            offset = start + len(line)
            if not line.strip():
                continue
            if _POINT.match(line):
                units.append(Unit(start, start + len(line.rstrip()), lead))
                continue
            line_lead = None
            for s, e, is_item in _line_units(text, start, start + len(line)):
                units.append(Unit(s, e, (line_lead if line_lead is not None else lead) if is_item else None))
                if not is_item:
                    line_lead = lead = len(units) - 1
    return units


def passage(text: str, units: list[Unit], cited: list[int]) -> str:
    """The text to show for the cited units (1-based numbers): each list item with its lead-in, units that
    follow each other as in the source, a gap marker between those that do not."""
    wanted = {n - 1 for n in cited if 1 <= n <= len(units)}
    wanted |= {units[i].lead for i in list(wanted) if units[i].lead is not None}
    parts, previous = [], None
    for i in sorted(wanted):
        if previous is not None:
            parts.append(text[units[previous].end:units[i].start] if i == previous + 1 else GAP)
        parts.append(text[units[i].start:units[i].end])
        previous = i
    return "".join(parts)
