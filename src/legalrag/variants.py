"""Chunking variants compared in step 0c. "default" defines the chunk set of the baseline
(EXPERIMENT.md); every other variant changes one setting and is embedded as its own run.

style: how much of the section path the header shows (see chunking/header.py);
collapse_repeats: merge consecutive same-label levels; max_tokens: split an article above it.
"""

DEFAULT = "default"
BASE = {"style": "last_k", "k": 3, "max_tokens": 1024, "collapse_repeats": False}
VARIANTS = {
    DEFAULT: BASE,
    "header-none": {**BASE, "style": "none"},
    "header-label": {**BASE, "style": "label"},
    "header-full": {**BASE, "style": "full"},
    "header-collapse": {**BASE, "collapse_repeats": True},
    "size-512": {**BASE, "max_tokens": 512},
}


def settings(variant: str) -> dict:
    if variant not in VARIANTS:
        raise ValueError(f"unknown variant {variant!r}; choose from {', '.join(VARIANTS)}")
    return VARIANTS[variant]


def embeddings_name(variant: str) -> str:
    """Stem of the embeddings files: the baseline keeps its original name `bge-m3-main`."""
    return "bge-m3-main" if variant == DEFAULT else f"bge-m3-{variant}"
