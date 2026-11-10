"""The short label of an article, as used in gold lists, search results and answers: "L1221-13" for the Code du travail,
"art 17" and "rct 65" for a GDPR article and recital.
"""


def article_label(source_code: str, kind: str, article_num: str) -> str:
    if source_code == "code_travail":
        return article_num
    return f"{'art' if kind == 'article' else 'rct'} {article_num}"


def split_label(label: str) -> tuple[str, str, str]:
    """Inverse of article_label: (source_code, kind, article_num)."""
    if label.startswith("art "):
        return "rgpd", "article", label[4:]
    if label.startswith("rct "):
        return "rgpd", "recital", label[4:]
    if label.startswith("Annexe"):
        return "code_travail", "annex", label
    return "code_travail", "article", label
