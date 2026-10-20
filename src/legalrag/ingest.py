from collections.abc import Callable
from pathlib import Path

from tokenizers import Tokenizer

from legalrag.chunking.header import build_header
from legalrag.chunking.split import pack, split_sentences
from legalrag.models import Article, Chunk

MAX_TOKENS = 1024
SAFETY_MARGIN = 4  # tokenising header + text together can differ slightly from the sum of parts

DOC_LABELS = {"code_travail": "Code du travail"}


def token_counter(tokenizer_path: Path) -> Callable[[str], int]:
    tk = Tokenizer.from_file(str(tokenizer_path))
    return lambda s: len(tk.encode(s, add_special_tokens=False).ids)


def build_chunks(
    articles: list[Article],
    count_tokens: Callable[[str], int],
    style: str = "last_k",
    k: int = 3,
    max_tokens: int = MAX_TOKENS,
) -> list[Chunk]:
    chunks = []
    for a in articles:
        header = build_header(
            DOC_LABELS[a.source_code],
            a.article_num,
            a.section_path.split(" > "),
            style=style,
            k=k,
            is_article=a.kind == "article",
        )
        prefix = header + "\n" if header else ""
        whole = prefix + a.body_text
        if count_tokens(whole) <= max_tokens:
            groups = [(a.body_text, False)]
        else:
            budget = max_tokens - count_tokens(prefix) - SAFETY_MARGIN
            groups = pack(split_sentences(a.body_text), budget, count_tokens)
        for i, (body, forced) in enumerate(groups):
            embed_text = prefix + body
            n = count_tokens(embed_text)
            extra = {}
            if len(groups) > 1:
                extra["split"] = True
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
