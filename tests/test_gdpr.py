from pathlib import Path

import pytest

from legalrag.ingest import build_chunks, header_inputs, token_counter
from legalrag.sources import gdpr
from legalrag.text import normalize_text

FIXTURE = Path(__file__).parent / "fixtures" / "gdpr_fr_excerpt.xhtml"
TOKENIZER = Path("data/raw/bge-m3-tokenizer.json")


def words(s: str) -> int:
    return len(s.split())


@pytest.fixture(scope="module")
def units():
    return {a.native_id: a for a in gdpr.parse(FIXTURE, "fr")}


def test_parse_finds_articles_and_recitals(units):
    assert sorted(units) == ["art_10", "art_12", "art_4", "art_5", "rct_3", "rct_4"]
    assert units["art_5"].uid == "rgpd:fr:art_5"
    assert units["rct_4"].kind == "recital"


def test_article_5_paragraphs_and_points(units):
    paragraphs = units["art_5"].body_text.split("\n\n")
    assert len(paragraphs) == 2
    lines = paragraphs[0].split("\n")
    assert lines[0] == "1. Les données à caractère personnel doivent être:"
    assert [line[:2] for line in lines[1:]] == [f"{c})" for c in "abcdef"]
    assert lines[1].startswith("a) traitées de manière licite, loyale et transparente")
    assert paragraphs[1].startswith("2. Le responsable du traitement est responsable")


def test_section_path_and_title(units):
    assert units["art_5"].section_path == "CHAPITRE II : Principes"
    assert units["art_5"].title.startswith("Principes relatifs au traitement")
    assert units["art_12"].section_path == (
        "CHAPITRE III : Droits de la personne concernée > Section 1 : Transparence et modalités"
    )


def test_definitions_keep_nested_points_in_one_group(units):
    groups = units["art_4"].body_text.split("\n\n")
    assert len(groups) == 27  # intro line + 26 definitions
    g16 = next(g for g in groups if g.startswith("16)"))
    lines = g16.split("\n")
    assert lines[0] == "16) «établissement principal»,"
    assert lines[1].startswith("a) en ce qui concerne un responsable du traitement")


def test_footnote_markers_and_recital_label_are_dropped(units):
    assert "(19)" not in units["art_4"].body_text
    assert not units["rct_3"].body_text.rstrip(".").endswith("(1)")
    assert units["rct_4"].body_text.startswith("Le traitement des données")


def test_single_paragraph_article(units):
    assert "\n" not in units["art_10"].body_text
    assert units["art_10"].body_text.startswith("Le traitement des données")


def test_gdpr_headers(units):
    chunks = {c.article_uid: c for c in build_chunks(list(units.values()), words)}
    assert chunks["rgpd:fr:art_5"].header_text == (
        "RGPD (règlement (UE) 2016/679), article 5 : Principes relatifs au traitement des "
        "données à caractère personnel. CHAPITRE II : Principes."
    )
    assert chunks["rgpd:fr:rct_4"].header_text == "RGPD, considérant 4."
    assert header_inputs(units["art_12"])[1].startswith("12 : Transparence")


def test_long_article_splits_between_whole_definitions(units):
    a = units["art_4"]
    chunks = build_chunks([a], words, max_tokens=500)
    assert len(chunks) > 1
    assert all(c.token_count <= 500 for c in chunks)
    originals = set(a.body_text.split("\n\n"))
    assert all(piece in originals for c in chunks for piece in c.body_text.split("\n\n"))
    assert normalize_text(" ".join(c.body_text for c in chunks)) == normalize_text(a.body_text)
    assert chunks[0].extra["paragraphs"].startswith("1-")


def test_oversize_paragraph_splits_at_points(units):
    a = units["art_5"]
    chunks = build_chunks([a], words, max_tokens=90)
    assert all(c.token_count <= 90 for c in chunks)
    assert any(c.body_text.startswith(("b)", "c)", "d)", "e)", "f)")) for c in chunks)
    assert normalize_text(" ".join(c.body_text for c in chunks)) == normalize_text(a.body_text)


def test_ingest_twice_gives_same_chunks(units):
    arts = list(units.values())
    assert build_chunks(arts, words, max_tokens=300) == build_chunks(arts, words, max_tokens=300)


@pytest.mark.skipif(not TOKENIZER.exists(), reason="bge-m3 tokenizer not downloaded")
def test_real_tokenizer_keeps_every_chunk_under_1024(units):
    chunks = build_chunks(list(units.values()), token_counter(TOKENIZER))
    assert max(c.token_count for c in chunks) <= 1024
    assert sum(c.article_uid == "rgpd:fr:art_4" for c in chunks) > 1
