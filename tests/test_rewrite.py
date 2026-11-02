import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from legalrag import evaluate, gold, rewrite
from legalrag.cli import app
from legalrag.questiongen import load_prompts

PROMPT = load_prompts(Path("prompts/query_rewrite.yaml"))["prompts"]["rewrite.v1"]
runner = CliRunner()


def test_the_prompt_sends_the_question_alone_as_the_user_turn():
    chat = rewrite.messages(PROMPT, "Mon patron peut me virer ?")
    assert [m["role"] for m in chat] == ["system", "user"] and chat[1]["content"] == "Mon patron peut me virer ?"


@pytest.mark.parametrize("answer, text, flags", [
    ("L’employeur peut-il licencier le salarié ?", "L'employeur peut-il licencier le salarié ?", []),
    ('« Question ? »\nautre ligne', "Question ?", ["several_lines"]),
    ("", "", ["empty"]),
    ("Que dit l'article L1221-13 ?", "Que dit l'article L1221-13 ?", ["article_number"]),
    (" ".join(["mot"] * 45), " ".join(["mot"] * 45), ["too_long"]),
])
def test_clean(answer, text, flags):
    assert rewrite.clean(answer, 40) == (text, flags)


def test_an_unusable_rewrite_falls_back_to_the_question_but_a_long_one_is_kept():
    assert rewrite.used_text("q", "r", ["empty"]) == "q"
    assert rewrite.used_text("q", "r", ["article_number"]) == "q"
    assert rewrite.used_text("q", "r", ["too_long", "several_lines"]) == "r"
    assert rewrite.used_text("q", "r", []) == "r"


def test_load_used_skips_the_run_line(tmp_path):
    path = tmp_path / "r.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in [{"type": "run"}, {"id": "a", "used": "x"}, {"id": "b", "used": "y"}]))
    assert rewrite.load_used(path) == {"a": "x", "b": "y"}


def test_the_dense_search_fuses_the_original_and_the_rewrite_when_given_both_vectors(monkeypatch):
    seen = []

    def fake(conn, run, lang, vector, keep, model):
        seen.append((vector, keep))
        return [("A", "ha"), ("B", "hb")] if vector == "orig" else [("B", "hb"), ("C", "hc")]

    monkeypatch.setattr(evaluate, "retrieve", fake)
    q = gold.GoldQuestion(id="a", question="q", lang="fr", group="A", kind="answerable",
                          gold=[gold.GoldArticle(source="code_travail", article="A", lang="fr", grade=2, content_hash="ha")],
                          split="dev", provenance=gold.Provenance(method="hand_written"))
    out = evaluate.retrieve_all(None, 1, [q], ["orig"], "dense", rewrite_vectors=["rw"])
    assert seen == [("orig", evaluate.FUSION_DEPTH), ("rw", evaluate.FUSION_DEPTH)]
    assert [label for label, _ in out["a"]] == ["B", "A", "C"]


def test_rewrites_work_with_the_dense_search_only_and_need_a_known_mode():
    assert runner.invoke(app, ["eval", "--search", "keyword", "--rewrites", "x.jsonl"]).exit_code != 0
    result = runner.invoke(app, ["eval", "--rewrites", "x.jsonl", "--rewrite-mode", "other"])
    assert result.exit_code != 0 and "replace or fuse" in result.output


def test_settings_record_the_rewrites():
    record = {"file_sha256": "s", "mode": "fuse", "searched_with_rewrite": 3}
    assert evaluate.settings(Path(__file__), "dev", "default", rewrites=record)["rewrites"] == record
