"""The quality gate of step 0e: the real search, metrics and answer checks on a frozen copy of the database.

Needs the fixture of `scripts/data/make_ci_fixture.py` (CI downloads it from a GitHub Release; see docs/CODE_MAP.md).
Without it the tests skip on a development machine and fail in CI.
"""

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from conftest import with_database

from legalrag.answering import rag
from legalrag.evaluation import cifixture, evaluate, gold
from legalrag.evaluation.questiongen import load_prompts
from legalrag.index import db
from legalrag.index.config import database_url

ROOT = Path(__file__).parents[2]
FIXTURE = Path(os.environ.get("LEGALRAG_CI_FIXTURE", ROOT / "data/ci/fixture"))
FLOORS = json.loads((ROOT / "eval/gate_floors.json").read_text())
REPLIES = json.loads((ROOT / "tests/fixtures/replies_dev.json").read_text())["replies"]


@pytest.fixture(scope="module")
def fixture():
    if not FIXTURE.exists():
        message = f"quality-gate fixture missing at {FIXTURE}"
        pytest.fail(message) if os.environ.get("CI") else pytest.skip(message)
    return cifixture.read(FIXTURE)


@pytest.fixture(scope="module")
def questions():
    return [q for q in gold.load_gold(ROOT / "eval/gold.jsonl") if q.split == "dev" and q.lang == "fr"]


@pytest.fixture(scope="module")
def loaded(database_name, fixture):
    url = with_database(database_url(), database_name)
    with db.connect(url) as conn:
        run_id = cifixture.load(conn, fixture)
        conn.commit()
    return url, run_id


def test_the_fixture_was_made_for_the_current_dev_questions(fixture, questions):
    assert fixture.questions == {q.id: q.question for q in questions}


def test_retrieval_stays_above_the_floors(loaded, fixture, questions):
    url, run_id = loaded
    with db.connect(url) as conn:
        ranked = evaluate.retrieve_all(conn, run_id, questions, fixture.question_vectors, "dense")
    summary = evaluate.summarize(evaluate.score(questions, ranked))
    means = {name: values[0] for name, values in summary["metrics"].items()}
    below = {name: (round(means[name], 3), floor) for name, floor in FLOORS.items() if name in means and means[name] < floor}
    assert not below, f"below the floors (measured, floor): {below}"
    assert {name for name in FLOORS if name != "note"} <= set(means)


class RecordedLLM:
    """Returns the reply recorded for the question; fails when the model should not have been called."""

    def __init__(self, replies: dict[str, str | None]):
        self.replies, self.question = replies, None

    def chat(self, messages, **kwargs):
        reply = self.replies[self.question]
        assert reply is not None, "the model was called for a question that was refused before the model"
        return SimpleNamespace(message=SimpleNamespace(content=reply), raw=SimpleNamespace(usage=None))


class RecordedEmbedder:
    def __init__(self, vectors: dict[str, np.ndarray]):
        self.vectors = vectors

    def encode_queries(self, texts, batch_size):
        return np.stack([self.vectors[t] for t in texts])


def test_replayed_model_replies_give_the_recorded_outcomes_and_citations(loaded, fixture, questions):
    url, run_id = loaded
    llm = RecordedLLM({})
    embedder = RecordedEmbedder({q.question: v for q, v in zip(questions, fixture.question_vectors, strict=True)})
    prompt = load_prompts(ROOT / "prompts/answer.yaml")["prompts"]["answer.v3"]
    engine = rag.AnswerEngine(
        retriever=rag.LegalRetriever(lambda: db.connect(url), run_id, embedder, "fr"), postprocessor=rag.NumberUnits(),
        llm=llm, prompt=prompt, model="deepseek-flash", prompt_id="answer.v3")
    differences = []
    for q in questions:
        recorded = REPLIES[q.id]
        llm.replies[q.question], llm.question = recorded["raw"], q.question
        result = engine.query(q.question).metadata["result"]
        cited = sorted({c.label for _, cs in (result.resolved.claims if result.resolved else []) for c in cs})
        if (result.outcome, cited) != (recorded["outcome"], recorded["cited"]):
            differences.append((q.id, result.outcome, cited, recorded["outcome"], recorded["cited"]))
    assert not differences, differences


def test_no_data_secrets_or_vectors_are_tracked_by_git():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
    forbidden = [f for f in files if f == ".env" or f.startswith("data/") or f.endswith((".npy", ".npz"))
                 or (f.endswith(".parquet") and not f.startswith("tests/fixtures/"))]
    assert not forbidden, forbidden
