import numpy as np
import pyarrow.parquet as pq
import pytest

from legalrag.embed import (
    DIM,
    check_chunks,
    embed_chunks,
    embed_text_hash,
    merge_shards,
)
from legalrag.models import Chunk


def make_chunk(i, text=None, tokens=10, index=0):
    text = text or f"header {i}\nbody {i}"
    return Chunk(
        article_uid=f"code_travail:fr:A{i}", chunk_index=index, lang="fr", header_text="h",
        body_text="b", embed_text=text, token_count=tokens,
    )


class StubEmbedder:
    """Vector derived from the text hash, deliberately not normalised."""

    def __init__(self, fail_after_calls=None):
        self.calls = []
        self.fail_after_calls = fail_after_calls

    def encode(self, texts, batch_size):
        if self.fail_after_calls is not None and len(self.calls) >= self.fail_after_calls:
            raise RuntimeError("out of memory")
        self.calls.append(list(texts))
        out = np.empty((len(texts), DIM), dtype=np.float32)
        for i, t in enumerate(texts):
            seed = int(embed_text_hash(t)[:8], 16)
            out[i] = np.random.default_rng(seed).normal(size=DIM) * 3
        return out

    def info(self):
        return {}


def test_embeds_every_chunk_and_merges_normalised_vectors(tmp_path):
    chunks = [make_chunk(i) for i in range(5)]
    assert embed_chunks(chunks, StubEmbedder(), tmp_path / "s", shard_size=2) == 5
    out = tmp_path / "out.parquet"
    assert merge_shards(chunks, tmp_path / "s", out, "m", "rev") == 5
    t = pq.read_table(out).to_pydict()
    assert t["article_uid"] == sorted(c.article_uid for c in chunks)
    assert set(t["model"]) == {"m"} and set(t["model_revision"]) == {"rev"} and set(t["dim"]) == {DIM}
    vectors = np.array(t["vector"])
    assert vectors.shape == (5, DIM)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)


def test_resume_computes_only_the_missing_chunks(tmp_path):
    chunks = [make_chunk(i, tokens=100 - i) for i in range(5)]
    shards = tmp_path / "s"
    with pytest.raises(RuntimeError):
        embed_chunks(chunks, StubEmbedder(fail_after_calls=1), shards, shard_size=2)
    assert len(list(shards.glob("shard_*.parquet"))) == 1  # one shard of 2 survived the crash
    rerun = StubEmbedder()
    assert embed_chunks(chunks, rerun, shards, shard_size=2) == 3
    assert sum(len(c) for c in rerun.calls) == 3
    assert merge_shards(chunks, shards, tmp_path / "out.parquet", "m", "r") == 5


def test_longest_chunks_go_first(tmp_path):
    chunks = [make_chunk(1, tokens=5), make_chunk(2, tokens=50), make_chunk(3, tokens=20)]
    stub = StubEmbedder()
    embed_chunks(chunks, stub, tmp_path / "s", shard_size=10)
    assert stub.calls[0] == [chunks[1].embed_text, chunks[2].embed_text, chunks[0].embed_text]


def test_changed_text_is_recomputed_and_the_old_vector_is_not_merged(tmp_path):
    shards = tmp_path / "s"
    embed_chunks([make_chunk(1, "old text")], StubEmbedder(), shards)
    new = [make_chunk(1, "new text")]
    rerun = StubEmbedder()
    assert embed_chunks(new, rerun, shards) == 1
    out = tmp_path / "out.parquet"
    merge_shards(new, shards, out, "m", "r")
    assert pq.read_table(out).to_pydict()["embed_text_hash"] == [embed_text_hash("new text")]


def test_merge_refuses_when_a_chunk_has_no_vector(tmp_path):
    chunks = [make_chunk(1), make_chunk(2)]
    embed_chunks(chunks[:1], StubEmbedder(), tmp_path / "s")
    with pytest.raises(ValueError, match="no up-to-date vector"):
        merge_shards(chunks, tmp_path / "s", tmp_path / "out.parquet", "m", "r")


def test_chunk_that_would_be_truncated_stops_the_run_before_any_work(tmp_path):
    stub = StubEmbedder()
    with pytest.raises(ValueError, match="truncated"):
        embed_chunks([make_chunk(1, tokens=1099)], stub, tmp_path / "s", max_seq_length=1100)
    assert stub.calls == []
    check_chunks([make_chunk(1, tokens=1098)], max_seq_length=1100)  # 1098 + 2 special tokens fits


def test_duplicate_keys_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        check_chunks([make_chunk(1), make_chunk(1)])


def test_wrong_vector_shape_is_rejected(tmp_path):
    class Short(StubEmbedder):
        def encode(self, texts, batch_size):
            return np.ones((len(texts), 8), dtype=np.float32)

    with pytest.raises(ValueError, match="shape"):
        embed_chunks([make_chunk(1)], Short(), tmp_path / "s")
