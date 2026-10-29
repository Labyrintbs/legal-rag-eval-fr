"""Embed chunks into sharded vector files, resume an interrupted run, merge into one parquet."""

import hashlib
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple, Protocol

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from legalrag.models import Chunk

MODEL = "BAAI/bge-m3"
DIM = 1024
MAX_SEQ_LENGTH = 1100
BASELINE_KEY = "bge-m3"


class ModelSpec(NamedTuple):
    name: str  # Hugging Face name
    query_prompt: str | None  # prompt name the model card asks for on queries (documents get none)
    max_seq_length: int  # chunk lengths are counted in bge-m3 tokens, so other tokenizers need headroom


# Key used in file names and options; every model here gives DIM-dimensional vectors.
EMBEDDING_MODELS = {
    BASELINE_KEY: ModelSpec(MODEL, None, MAX_SEQ_LENGTH),
    "qwen3-embedding-0.6b": ModelSpec("Qwen/Qwen3-Embedding-0.6B", "query", 2048),
}
SPECIAL_TOKENS = 2  # the model adds a start and an end token to every text
SHARD_SIZE = 1000
BATCH_SIZE = 16
NORM_TOLERANCE = 1e-3
DIRTY = " (uncommitted changes)"  # appended to the git hash when the working tree is not clean


class Embedder(Protocol):
    def encode(self, texts: list[str], batch_size: int) -> np.ndarray: ...

    def encode_queries(self, texts: list[str], batch_size: int) -> np.ndarray: ...

    def info(self) -> dict: ...


def embed_text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _key(c: Chunk) -> tuple[str, int]:
    return c.article_uid, c.chunk_index


def check_chunks(chunks: list[Chunk], max_seq_length: int = MAX_SEQ_LENGTH) -> None:
    keys = [_key(c) for c in chunks]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate (article_uid, chunk_index) in the chunk set")
    too_long = [c for c in chunks if c.token_count + SPECIAL_TOKENS > max_seq_length]
    if too_long:
        raise ValueError(
            f"{len(too_long)} chunks would be truncated at max_seq_length={max_seq_length}, "
            f"first: {_key(too_long[0])}"
        )


def _shard_files(shard_dir: Path) -> list[Path]:
    return sorted(shard_dir.glob("shard_*.parquet"))


def _read_shards(shard_dir: Path) -> dict[tuple[str, int], tuple[str, np.ndarray]]:
    """(article_uid, chunk_index) -> (embed_text_hash, vector) over all shards."""
    rows: dict[tuple[str, int], tuple[str, np.ndarray]] = {}
    for path in _shard_files(shard_dir):
        t = pq.read_table(path).to_pydict()
        for uid, idx, h, vec in zip(
            t["article_uid"], t["chunk_index"], t["embed_text_hash"], t["vector"], strict=True
        ):
            rows[(uid, idx)] = (h, np.asarray(vec, dtype=np.float32))
    return rows


def _write_shard(shard_dir: Path, number: int, chunks: list[Chunk], vectors: np.ndarray) -> None:
    table = pa.table(
        {
            "article_uid": [c.article_uid for c in chunks],
            "chunk_index": pa.array([c.chunk_index for c in chunks], pa.int32()),
            "embed_text_hash": [embed_text_hash(c.embed_text) for c in chunks],
            "vector": pa.FixedSizeListArray.from_arrays(pa.array(vectors.ravel()), DIM),
        }
    )
    target = shard_dir / f"shard_{number:04d}.parquet"
    part = target.with_name(target.name + ".part")  # a crash must not leave a half-written shard
    pq.write_table(table, part)
    part.replace(target)


def embed_chunks(
    chunks: list[Chunk],
    embedder: Embedder,
    shard_dir: Path,
    shard_size: int = SHARD_SIZE,
    batch_size: int = BATCH_SIZE,
    max_seq_length: int = MAX_SEQ_LENGTH,
    progress: Callable[[int, int], None] | None = None,
) -> int:
    """Embed the chunks not yet in shard_dir; return how many were computed."""
    check_chunks(chunks, max_seq_length)
    shard_dir.mkdir(parents=True, exist_ok=True)
    done = {k: h for k, (h, _) in _read_shards(shard_dir).items()}
    todo = [c for c in chunks if done.get(_key(c)) != embed_text_hash(c.embed_text)]
    # Longest first: an out-of-memory error shows up in the first shard, not after an hour.
    todo.sort(key=lambda c: -c.token_count)
    next_shard = len(_shard_files(shard_dir))
    for start in range(0, len(todo), shard_size):
        batch = todo[start : start + shard_size]
        vectors = np.asarray(
            embedder.encode([c.embed_text for c in batch], batch_size), dtype=np.float32
        )
        if vectors.shape != (len(batch), DIM):
            raise ValueError(f"embedder returned shape {vectors.shape}, expected {(len(batch), DIM)}")
        # Normalise here in float32 (the model runs in fp16) so cosine equals a dot product.
        vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
        _write_shard(shard_dir, next_shard, batch, vectors)
        next_shard += 1
        if progress:
            progress(min(start + shard_size, len(todo)), len(todo))
    return len(todo)


def merge_shards(
    chunks: list[Chunk], shard_dir: Path, out_path: Path, model: str, revision: str
) -> int:
    """Write one parquet with a row per chunk, after checking every chunk has a valid vector."""
    rows = _read_shards(shard_dir)
    ordered = sorted(chunks, key=_key)
    vectors = np.empty((len(ordered), DIM), dtype=np.float32)
    for i, c in enumerate(ordered):
        found = rows.get(_key(c))
        if found is None or found[0] != embed_text_hash(c.embed_text):
            raise ValueError(f"no up-to-date vector for {_key(c)}")
        vectors[i] = found[1]
    if not np.isfinite(vectors).all():
        raise ValueError("NaN or infinite value in the vectors")
    norms = np.linalg.norm(vectors, axis=1)
    if np.abs(norms - 1).max() > NORM_TOLERANCE:
        raise ValueError(f"vector norm outside 1 +/- {NORM_TOLERANCE}")
    n = len(ordered)
    table = pa.table(
        {
            "article_uid": [c.article_uid for c in ordered],
            "chunk_index": pa.array([c.chunk_index for c in ordered], pa.int32()),
            "lang": [c.lang for c in ordered],
            "model": [model] * n,
            "model_revision": [revision] * n,
            "dim": pa.array([DIM] * n, pa.int32()),
            "embed_text_hash": [embed_text_hash(c.embed_text) for c in ordered],
            "vector": pa.FixedSizeListArray.from_arrays(pa.array(vectors.ravel()), DIM),
        }
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, out_path)
    return n


def git_commit() -> str:
    """HEAD hash for run.json, flagged when the working tree has uncommitted changes."""

    def git(*args: str) -> str:
        out = subprocess.run(["git", *args], check=True, capture_output=True, text=True)
        return out.stdout.strip()

    return git("rev-parse", "HEAD") + (DIRTY if git("status", "--short") else "")


def write_run_json(path: Path, info: dict) -> None:
    path.write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n")


class SentenceTransformerEmbedder:
    """An embedding model in fp16 on the GPU, or in float32 on the CPU. Imports torch lazily."""

    def __init__(self, device: str = "cuda", max_seq_length: int | None = None, model_key: str = BASELINE_KEY) -> None:
        import torch
        from huggingface_hub import model_info
        from sentence_transformers import SentenceTransformer

        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        if device not in ("cuda", "cpu"):
            raise ValueError(f"device must be cuda, cpu or auto, got {device}")
        if device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA is not available; use --device cpu or auto")
        self.device = device
        self.spec = EMBEDDING_MODELS[model_key]
        self.revision = model_info(self.spec.name).sha
        self.model = SentenceTransformer(
            self.spec.name,
            device=device,
            revision=self.revision,
            model_kwargs={"torch_dtype": torch.float16 if device == "cuda" else torch.float32},
        )
        self.model.max_seq_length = max_seq_length or self.spec.max_seq_length
        if device == "cuda":
            torch.cuda.reset_peak_memory_stats()

    def encode(self, texts: list[str], batch_size: int) -> np.ndarray:
        return self.model.encode(
            texts, batch_size=batch_size, convert_to_numpy=True, show_progress_bar=False
        )

    def encode_queries(self, texts: list[str], batch_size: int) -> np.ndarray:
        return self.model.encode(
            texts, batch_size=batch_size, convert_to_numpy=True, show_progress_bar=False,
            prompt_name=self.spec.query_prompt,
        )

    def info(self) -> dict:
        import sentence_transformers
        import torch

        info = {
            "model": self.spec.name,
            "model_revision": self.revision,
            "device": self.device,
            "torch": torch.__version__,
            "sentence_transformers": sentence_transformers.__version__,
        }
        if self.device == "cuda":
            info["gpu"] = torch.cuda.get_device_name(0)
            info["peak_vram_mb"] = round(torch.cuda.max_memory_allocated() / 2**20)
        return info
