from legalrag.text import normalize_text

STYLES = ("none", "label", "last_k", "full")


def build_header(
    doc_label: str,
    unit_label: str,
    path_titles: list[str],
    style: str = "last_k",
    k: int = 3,
    is_article: bool = True,
) -> str:
    """Heading line placed before the body in the text that is embedded."""
    if style not in STYLES:
        raise ValueError(f"unknown header style: {style}")
    if style == "none":
        return ""
    unit = f"article {unit_label}" if is_article else unit_label
    header = f"{doc_label}, {normalize_text(unit)}"
    titles = [t for t in (normalize_text(t) for t in path_titles) if t]
    if style == "last_k":
        titles = titles[-k:]
    elif style == "label":
        titles = []
    if titles:
        header += ". " + " > ".join(titles)
    return header if header.endswith(".") else header + "."
