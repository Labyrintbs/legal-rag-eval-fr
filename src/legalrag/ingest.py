import re
from collections.abc import Callable
from pathlib import Path

from tokenizers import Tokenizer

from legalrag.chunking.header import build_header
from legalrag.chunking.split import pack, split_paragraphs, split_sentences
from legalrag.models import Article, Chunk

MAX_TOKENS = 1024
SAFETY_MARGIN = 4  # tokenising header + text together can differ slightly from the sum of parts
_PARA = re.compile(r"(\d+)[.)] ")  # "2. ..." paragraphs and "16) ..." definitions

RGPD_LABELS = {
    "fr": ("RGPD (règlement (UE) 2016/679)", "RGPD", "considérant"),
    "en": ("GDPR (Regulation (EU) 2016/679)", "GDPR", "recital"),
}


def header_inputs(a: Article) -> tuple[str, str, bool]:
    """(doc_label, unit_label, is_article) for the header builder."""
    if a.source_code == "code_travail":
        return "Code du travail", a.article_num, a.kind == "article"
    full, short, recital = RGPD_LABELS[a.lang]
    if a.kind == "recital":
        return short, f"{recital} {a.article_num}", False
    return full, f"{a.article_num} : {a.title}", True


def split_article(
    a: Article, budget: int, count_tokens: Callable[[str], int]
) -> list[tuple[str, bool]]:
    if a.source_code == "code_travail":
        return pack(split_sentences(a.body_text), budget, count_tokens)
    # GDPR: whole paragraphs first, then points inside a paragraph, then sentences.
    def by_sentences(line: str) -> list[tuple[str, bool]]:
        return pack(split_sentences(line), budget, count_tokens)

    def by_points(paragraph: str) -> list[tuple[str, bool]]:
        lines = split_paragraphs(paragraph, "\n")
        return pack(lines, budget, count_tokens, "\n", fallback=by_sentences)

    return pack(
        split_paragraphs(a.body_text), budget, count_tokens, "\n\n", fallback=by_points
    )


def token_counter(tokenizer_path: Path) -> Callable[[str], int]:
    tk = Tokenizer.from_file(str(tokenizer_path))
    return lambda s: len(tk.encode(s, add_special_tokens=False).ids)


def build_chunks(
    articles: list[Article],
    count_tokens: Callable[[str], int],
    style: str = "last_k",
    k: int = 3,
    max_tokens: int = MAX_TOKENS,
    collapse_repeats: bool = False,
) -> list[Chunk]:
    chunks = []
    for a in articles:
        doc_label, unit_label, is_article = header_inputs(a)
        header = build_header(
            doc_label,
            unit_label,
            a.section_path.split(" > "),
            style=style,
            k=k,
            is_article=is_article,
            collapse_repeats=collapse_repeats,
        )
        prefix = header + "\n" if header else ""
        whole = prefix + a.body_text
        if count_tokens(whole) <= max_tokens:
            groups = [(a.body_text, False)]
        else:
            budget = max_tokens - count_tokens(prefix) - SAFETY_MARGIN
            groups = split_article(a, budget, count_tokens)
        for i, (body, forced) in enumerate(groups):
            embed_text = prefix + body
            n = count_tokens(embed_text)
            extra = {}
            if len(groups) > 1:
                extra["split"] = True
                if a.source_code == "rgpd":
                    nums = [m.group(1) for p in body.split("\n\n") if (m := _PARA.match(p))]
                    if nums:
                        extra["paragraphs"] = f"{nums[0]}-{nums[-1]}"
            if forced:
                extra["word_windows"] = True
            if a.kind == "annex":
                extra["annex"] = True
            if n > max_tokens:
                extra["over_limit"] = True
            chunks.append(
                Chunk(
                    article_uid=a.uid,
                    chunk_index=i,
                    lang=a.lang,
                    header_text=header,
                    body_text=body,
                    embed_text=embed_text,
                    token_count=n,
                    extra=extra,
                )
            )
    return chunks
