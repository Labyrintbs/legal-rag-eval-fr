"""The comparison with LlamaIndex's own `CitationQueryEngine` (decision 5 of 0006): its answer, a text with [n] marks
that name numbered source chunks, is turned into the same rows as our answer path, so that the same judge and the
same metrics (`answermetrics`) score both.
"""

import re

from legalrag.chunking.split import split_sentences

MARK = re.compile(r"\[(?:Sources?\s+)?(\d+(?:\s*,\s*\d+)*)\]")  # the model writes "[1]" or, often, "[Source 1]"
SOURCE_PREFIX = re.compile(r"^Source \d+:\n")


def cited_sentences(text: str, sources: int) -> tuple[list[tuple[str, list[int]]], int]:
    """(sentence without its marks, the source numbers it cites) for every sentence that cites a source, and the
    number of sentences that cite none. Numbers that name no source are dropped, as our resolver drops ids."""
    cited, uncited = [], 0
    for sentence in (s for line in text.split("\n") for s in split_sentences(line)):
        numbers = [int(n) for group in MARK.findall(sentence) for n in re.findall(r"\d+", group)]
        numbers = [n for n in dict.fromkeys(numbers) if 1 <= n <= sources]
        plain = MARK.sub("", sentence).strip()
        if not plain:
            continue
        if numbers:
            cited.append((re.sub(r"\s+([.;,:])", r"\1", plain), numbers))
        else:
            uncited += 1
    return cited, uncited


def source_passage(text: str) -> str:
    """The text of a citation node without the "Source n:" line the engine adds."""
    return SOURCE_PREFIX.sub("", text).strip()


def render(cited: list[tuple[str, list[int]]], sources: list[tuple[str, str]]) -> str:
    """The format of `answer.render`: the claims with numbered marks, then the cited passages."""
    notes, lines = [], []
    for sentence, numbers in cited:
        marks = []
        for n in numbers:
            label, passage = sources[n - 1]
            notes.append(f"[{len(notes) + 1}] {label} - {passage}")
            marks.append(f"[{len(notes)}]")
        lines.append(f"{sentence} {''.join(marks)}")
    return "\n".join(lines) + "\n\n" + "\n".join(notes)
