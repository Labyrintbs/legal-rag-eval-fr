import json
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from legalrag import cli, embed, variants
from legalrag.chunking.header import STYLES
from legalrag.ingest import build_chunks
from legalrag.sources import legi

FIXTURE = Path(__file__).parent / "fixtures" / "code_travail_sample.json"
runner = CliRunner()


def words(s: str) -> int:
    return len(s.split())


@pytest.fixture(scope="module")
def articles():
    return legi.to_articles(pd.DataFrame(json.loads(FIXTURE.read_text())))


def test_every_variant_is_accepted_by_the_chunker():
    for settings in variants.VARIANTS.values():
        assert settings["style"] in STYLES
        assert set(settings) - {"sentences"} == set(variants.BASE)


def test_each_variant_changes_exactly_one_setting_from_the_default():
    for name, settings in variants.VARIANTS.items():
        changed = {key for key in settings if settings[key] != variants.BASE.get(key)}
        assert len(changed) == (0 if name == variants.DEFAULT else 1), name


def test_baseline_keeps_its_embeddings_file_name():
    assert variants.embeddings_name(variants.DEFAULT) == "bge-m3-main"
    assert variants.embeddings_name("header-none") == "bge-m3-header-none"


def test_file_names_carry_the_model_key():
    assert variants.embeddings_name(variants.DEFAULT, "qwen3-embedding-0.6b") == "qwen3-embedding-0.6b-main"
    assert variants.embeddings_name("size-512", "qwen3-embedding-0.6b") == "qwen3-embedding-0.6b-size-512"


def test_unknown_model_is_refused():
    for command in ("embed", "load-embeddings", "sanity", "eval"):
        option = "--embedding-model" if command == "eval" else "--model"
        result = runner.invoke(cli.app, [command, option, "nothing"])
        assert result.exit_code != 0 and "unknown model" in result.output, command


def test_registered_models_have_a_hugging_face_name_and_room_for_longer_tokenisation():
    spec = embed.EMBEDDING_MODELS
    assert spec[embed.BASELINE_KEY].name == embed.MODEL and spec[embed.BASELINE_KEY].query_prompt is None
    assert spec["qwen3-embedding-0.6b"].query_prompt == "query"
    assert all(s.max_seq_length >= embed.MAX_SEQ_LENGTH for s in spec.values())


def test_unknown_variant_is_refused():
    with pytest.raises(ValueError, match="unknown variant"):
        variants.settings("header-fancy")
    result = runner.invoke(cli.app, ["embed", "--variant", "header-fancy"])
    assert result.exit_code != 0 and "unknown variant" in result.output


def single_chunks(chunks):
    """article uid -> chunk, for the articles that stay in one chunk."""
    counts = {}
    for c in chunks:
        counts[c.article_uid] = counts.get(c.article_uid, 0) + 1
    return {c.article_uid: c for c in chunks if counts[c.article_uid] == 1}


def test_header_variants_change_the_embedded_text_only_in_the_header(articles):
    # a longer header leaves less room, so the split points of long articles may move: compare whole articles
    plain = [name for name in variants.VARIANTS if "sentences" not in variants.settings(name)]
    one = {name: single_chunks(build_chunks(articles, words, **variants.settings(name))) for name in plain}
    kept = set.intersection(*(set(chunks) for chunks in one.values()))
    assert kept
    for uid in kept:
        assert len({chunks[uid].body_text for chunks in one.values()}) == 1
        assert one["header-none"][uid].embed_text == one["header-none"][uid].body_text
        sizes = [len(one[name][uid].header_text) for name in ("header-none", "header-label", variants.DEFAULT, "header-full")]
        assert sizes == sorted(sizes)


def test_a_smaller_limit_splits_more_articles(articles):
    base = build_chunks(articles, words, **variants.settings(variants.DEFAULT))
    small = build_chunks(articles, words, **{**variants.BASE, "max_tokens": 40})
    assert len(small) > len(base)


def test_a_sentence_is_added_after_the_section_titles_and_only_for_its_article(articles):
    a, b = articles[0], articles[1]
    plain = build_chunks([a, b], words, **variants.BASE)
    with_sentence = build_chunks([a, b], words, sentences={a.uid: "Une question simple ?"}, **variants.BASE)
    assert with_sentence[0].header_text == plain[0].header_text + " Une question simple ?"
    assert with_sentence[0].embed_text.startswith(with_sentence[0].header_text + "\n")
    assert [c.header_text for c in with_sentence if c.article_uid == b.uid] == [c.header_text for c in plain if c.article_uid == b.uid]
    assert build_chunks([a], words, **{**variants.BASE, "style": "none"}, sentences={a.uid: "x ?"})[0].header_text == ""


def test_the_llm_variant_names_its_sentences_file_and_needs_it(tmp_path, monkeypatch):
    settings = variants.settings("header-llm")
    assert settings["sentences"] == "heading-sentences-v3" and {k: v for k, v in settings.items() if k != "sentences"} == variants.BASE
    monkeypatch.setattr(cli, "SENTENCES", tmp_path)
    with pytest.raises(Exception, match="missing"):
        cli._chunk_kwargs(settings)
    (tmp_path / "heading-sentences-v3.jsonl").write_text(json.dumps({"uid": "u", "sentence": "Q ?", "flags": []}))
    assert cli._chunk_kwargs(settings)["sentences"] == {"u": "Q ?"}
    assert len(cli._sentences_sha256(settings)) == 64 and cli._sentences_sha256(variants.settings("size-512")) is None
