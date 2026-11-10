"""What the command modules share: the data paths, the option types and the helpers that build chunks."""

import hashlib
from pathlib import Path

import typer

from legalrag.corpus import variants
from legalrag.corpus.ingest import build_chunks, token_counter
from legalrag.corpus.sources import gdpr, legi
from legalrag.experiments import headsentence
from legalrag.index import embed

RAW = Path("data/raw")
PARQUET = RAW / "legi_vincegx33_train.parquet"
TOKENIZER = RAW / "bge-m3-tokenizer.json"
EMBEDDINGS = Path("data/embeddings")
SENTENCES = Path("data/sentences")
PROFILES = Path("docs/data_profiles")
SOURCES = ("legi", "gdpr")
VARIANT_OPTION = typer.Option(help="Chunking variant (names in variants.py)")
MODEL_OPTION = typer.Option(help="Embedding model key (embed.EMBEDDING_MODELS)")


def model_spec(model: str) -> embed.ModelSpec:
    if model not in embed.EMBEDDING_MODELS:
        raise typer.BadParameter(f"unknown model {model!r}; choose from {', '.join(embed.EMBEDDING_MODELS)}")
    return embed.EMBEDDING_MODELS[model]


def variant_settings(variant: str) -> dict:
    try:
        return variants.settings(variant)
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e


def sentences_path(settings: dict) -> Path | None:
    return SENTENCES / f"{settings['sentences']}.jsonl" if "sentences" in settings else None


def chunk_kwargs(settings: dict) -> dict:
    """build_chunks arguments of a variant: a sentences name becomes the sentences of its file."""
    path = sentences_path(settings)
    if path is None:
        return settings
    if not path.exists():
        raise typer.BadParameter(f"{path} is missing: write it with scripts/heading_sentences_all.py or download it")
    return {**settings, "sentences": headsentence.load_sentences(path)}


def sentences_sha256(settings: dict) -> str | None:
    path = sentences_path(settings)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path else None


def variant_chunks(variant: str, limit: int | None) -> tuple[list, dict]:
    """The chunks of a variant (Code du travail, GDPR French and English) and its recorded settings; a limit
    takes an even sample of about that many."""
    chunk_settings = variant_settings(variant)
    kwargs = chunk_kwargs(chunk_settings)
    count = token_counter(TOKENIZER)
    chunks = build_chunks(legi.to_articles(legi.read(PARQUET)), count, **kwargs)
    for lang in ("fr", "en"):
        chunks += build_chunks(gdpr.parse(RAW / f"gdpr_{lang}.xhtml", lang), count, **kwargs)
    if limit:
        chunks = chunks[:: max(1, len(chunks) // limit)][:limit]
    return chunks, chunk_settings


def progress(done: int, total: int) -> None:
    typer.echo(f"encoded {done}/{total}")


def check_source(source: str) -> None:
    if source not in SOURCES:
        raise typer.BadParameter(f"source must be one of {SOURCES}")
