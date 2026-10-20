from legalrag.text import normalize_text

STYLES = ("none", "label", "last_k", "full")


def _label(title: str) -> str:
    return title.split(" : ")[0].strip().lower() if " : " in title else title.lower()


def collapse_repeated_levels(titles: list[str]) -> list[str]:
    """Keep the last of each run of levels with the same label ("Section 3", "Section 3").

    A level cannot nest in one of its own type, so a run is one node whose title was reworded;
    the source lists the wordings oldest first.
    """
    out: list[str] = []
    for t in titles:
        if out and _label(out[-1]) == _label(t):
            out[-1] = t
        else:
            out.append(t)
    return out


def build_header(
    doc_label: str,
    unit_label: str,
    path_titles: list[str],
    style: str = "last_k",
    k: int = 3,
    is_article: bool = True,
    collapse_repeats: bool = False,
) -> str:
    """Heading line placed before the body in the text that is embedded."""
    if style not in STYLES:
        raise ValueError(f"unknown header style: {style}")
    if style == "none":
        return ""
    unit = f"article {unit_label}" if is_article else unit_label
    header = f"{doc_label}, {normalize_text(unit)}"
    titles = [t for t in (normalize_text(t) for t in path_titles) if t]
    if collapse_repeats:
        titles = collapse_repeated_levels(titles)
    if style == "last_k":
        titles = titles[-k:]
    elif style == "label":
        titles = []
    if titles:
        header += ". " + " > ".join(titles)
    return header if header.endswith(".") else header + "."
