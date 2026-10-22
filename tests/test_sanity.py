import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from legalrag.sanity import load, rank


class StubEmbedder:
    """Maps each question text to a fixed vector, deliberately not normalised."""

    def __init__(self, table):
        self.table = table

    def encode(self, texts, batch_size):
        return np.array([self.table[t] for t in texts], dtype=np.float32)

    def info(self):
        return {}


VECTORS = np.eye(4, dtype=np.float32)
LABELS = ["L1", "L2", "rgpd:fr:art_5", "L4"]


def test_expected_article_in_top_is_ok_and_sorted_by_cosine():
    stub = StubEmbedder({"q": [0.1, 0, 3, 0.5]})
    (r,) = rank(LABELS, VECTORS, stub, [("q", "rgpd:fr:art_5")], top=2)
    assert [label for label, _ in r.hits] == ["rgpd:fr:art_5", "L4"]
    assert r.hits[0][1] > r.hits[1][1]
    assert r.hits[0][1] <= 1.0  # the query was normalised
    assert r.ok


def test_expected_article_outside_top_is_not_ok():
    stub = StubEmbedder({"q": [0, 0, 1, 0]})
    (r,) = rank(LABELS, VECTORS, stub, [("q", "L1")], top=1)
    assert not r.ok


def test_load_returns_uids_and_vector_matrix(tmp_path):
    path = tmp_path / "e.parquet"
    pq.write_table(
        pa.table(
            {
                "article_uid": ["a", "b"],
                "vector": pa.FixedSizeListArray.from_arrays(pa.array(np.eye(2, dtype=np.float32).ravel()), 2),
            }
        ),
        path,
    )
    uids, vectors = load(path)
    assert uids == ["a", "b"]
    assert vectors.shape == (2, 2)
