import json
from pathlib import Path

import pandas as pd
import pytest

from legalrag.chunking.header import build_header, collapse_repeated_levels
from legalrag.chunking.split import pack, split_sentences
from legalrag.ingest import build_chunks, token_counter
from legalrag.sources import legi
from legalrag.text import normalize_text

FIXTURE = Path(__file__).parent / "fixtures" / "code_travail_sample.json"
TOKENIZER = Path("data/raw/bge-m3-tokenizer.json")


def words(s: str) -> int:
    return len(s.split())


@pytest.fixture(scope="module")
def articles():
    return legi.to_articles(pd.DataFrame(json.loads(FIXTURE.read_text())))


def by_num(articles, num):
    return next(a for a in articles if a.article_num == num)


def test_normalize_text_removes_invisible_marks_and_collapses_spaces():
    assert normalize_text(" a‎b \r\n c d ") == "ab c d"


PATH = ["Partie L", "Livre II", "Section 1 : Rupture.", "Sous-section 1 : Démission."]


def test_header_styles():
    assert build_header("Code du travail", "L1", PATH, "none") == ""
    assert build_header("Code du travail", "L1", PATH, "label") == "Code du travail, article L1."
    assert build_header("Code du travail", "L1", PATH, "last_k", k=2) == (
        "Code du travail, article L1. Section 1 : Rupture. > Sous-section 1 : Démission."
    )
    assert build_header("Code du travail", "L1", PATH, "full").count(" > ") == 3


def test_header_fewer_levels_than_k_and_no_double_stop():
    h = build_header("Code du travail", "L1", ["Partie L", "Livre II."], "last_k", k=3)
    assert h == "Code du travail, article L1. Partie L > Livre II."


def test_header_annex_has_no_article_word():
    h = build_header("Code du travail", "Annexe III", ["Partie R"], is_article=False)
    assert h == "Code du travail, Annexe III. Partie R."


def test_header_cleans_carriage_return_in_titles():
    h = build_header("Code du travail", "L1", ["Section 1 :\r\nRupture"], "last_k")
    assert "\r" not in h and "Section 1 : Rupture" in h


def test_collapse_keeps_last_of_a_run_only():
    titles = ["Partie R", "Titre V : a", "TITRE V : b", "Titre V : c", "Chapitre Ier : x",
              "Section 3 : y", "Sous-section 1 : z", "Section 3 : w"]
    assert collapse_repeated_levels(titles) == [
        "Partie R", "Titre V : c", "Chapitre Ier : x", "Section 3 : y", "Sous-section 1 : z",
        "Section 3 : w",
    ]


def test_header_collapse_option_changes_only_the_header():
    path = ["Partie R", "Livre III : old", "Livre III : new", "Titre VI : t", "Titre VI : u"]
    plain = build_header("Code du travail", "L1", path, "full")
    collapsed = build_header("Code du travail", "L1", path, "full", collapse_repeats=True)
    assert "Livre III : old" in plain and "Livre III : old" not in collapsed
    assert collapsed == "Code du travail, article L1. Partie R > Livre III : new > Titre VI : u."


SITE_PATHS = json.loads((FIXTURE.parent / "legifrance_site_paths.json").read_text())


@pytest.mark.parametrize("article_id", [k for k in SITE_PATHS if not k.startswith("_")])
def test_collapse_reproduces_legifrance_path(article_id):
    case = SITE_PATHS[article_id]
    got = [normalize_text(t) for t in collapse_repeated_levels(case["data"])]
    assert got == case["site"], case["article_num"]


@pytest.mark.parametrize(
    "ref",
    ["L. 8113-6", "R. 4312-1", "D. 1234-5", "art. 5", "al. 2", "n° 2006-340"],
)
def test_abbreviations_are_not_split(ref):
    text = f"Voir {ref} du code. Le salarié part."
    assert split_sentences(text) == [f"Voir {ref} du code.", "Le salarié part."]


def test_pack_respects_budget_and_rejoins():
    pieces = [f"Phrase numéro {i} avec quelques mots." for i in range(30)]
    groups = pack(pieces, budget=40, count_tokens=words)
    assert len(groups) > 1
    assert all(words(g) <= 40 for g, _ in groups)
    assert " ".join(g for g, _ in groups) == " ".join(pieces)


def test_pack_falls_back_to_word_windows():
    groups = pack(["mot " * 100], budget=30, count_tokens=words)
    assert all(forced for _, forced in groups)
    assert all(words(g) <= 30 for g, _ in groups)


def test_article_kinds_and_cleaning(articles):
    assert by_num(articles, "L1251-33-1").kind == "article"  # source number had a leading space
    assert by_num(articles, "R*3231-4").kind == "article"
    assert by_num(articles, "Annexe III").kind == "annex"
    # source section_path is stored unchanged
    assert "\r" in by_num(articles, "L2152-1").section_path


def test_identical_bodies_stay_separate_with_different_headers(articles):
    chunks = build_chunks(articles, words, max_tokens=100_000)
    a, b = by_num(articles, "L1232-3"), by_num(articles, "L1233-12")
    assert a.body_text == b.body_text
    ca = next(c for c in chunks if c.article_uid == a.uid)
    cb = next(c for c in chunks if c.article_uid == b.uid)
    assert ca.header_text != cb.header_text
    assert "licenciement" in cb.header_text.lower()


def test_long_article_splits_within_limit_and_rejoins(articles):
    a = by_num(articles, "L6123-5")
    chunks = [c for c in build_chunks([a], words, max_tokens=300) if c.article_uid == a.uid]
    assert len(chunks) > 1
    assert all(c.token_count <= 300 for c in chunks)
    assert all(c.header_text and c.body_text.strip() for c in chunks)
    assert normalize_text(" ".join(c.body_text for c in chunks)) == a.body_text


def test_ingest_twice_gives_same_chunks(articles):
    first = build_chunks(articles, words, max_tokens=300)
    second = build_chunks(articles, words, max_tokens=300)
    assert first == second
    keys = [(c.article_uid, c.chunk_index) for c in first]
    assert len(keys) == len(set(keys))


@pytest.mark.skipif(not TOKENIZER.exists(), reason="bge-m3 tokenizer not downloaded")
def test_real_tokenizer_keeps_every_chunk_under_1024(articles):
    chunks = build_chunks(articles, token_counter(TOKENIZER))
    assert max(c.token_count for c in chunks) <= 1024
    assert len(chunks) > len(articles)  # the fixture holds long articles that must split
