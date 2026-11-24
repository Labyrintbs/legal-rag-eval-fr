"""The demo pages (step 0f, part 4): served with their security headers, an English text for every French one, and
example questions that are real dev questions."""

import re
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from legalrag.evaluation import gold
from legalrag.web import app as web
from legalrag.web import examples, warm

STATIC = Path(web.__file__).parent / "static"
ROOT = Path(__file__).parents[2]
PAGES = ("index.html", "method.html", "data.html", "privacy.html", "history.html")


def client(**kwargs):
    return TestClient(web.create_app(None, None, **kwargs))


def test_the_pages_and_their_files_are_served_with_security_headers():
    c = client()
    for path, marker in (("/", "Posez une question"), ("/method", "ce que nous avons mesuré"), ("/data", "Les données"), ("/privacy", "Qui est responsable"), ("/history", "Historique de vos questions"),
                         ("/static/app.js", "use strict"), ("/static/texts_en.js", "const EN"), ("/static/style.css", "--accent")):
        reply = c.get(path)
        assert reply.status_code == 200 and marker in reply.text, path
        assert reply.headers["x-content-type-options"] == "nosniff"
        assert "default-src 'self'" in reply.headers["content-security-policy"]
    assert c.get("/static/missing.js").status_code == 404


def test_the_api_documentation_keeps_its_own_page_without_the_strict_policy():
    assert "content-security-policy" not in client().get("/api/docs").headers


def test_the_examples_route_sends_the_given_examples_or_an_empty_list():
    assert client().get("/examples").json() == []
    given = [{"question": "Quelle durée ?", "label": {"fr": "Durée", "en": "Duration"}}]
    assert client(examples=given).get("/examples").json() == given


def script() -> str:
    return (STATIC / "app.js").read_text()


def test_every_element_the_script_looks_for_exists_in_a_page():
    ids = set(re.findall(r'getElementById\("([\w-]+)"\)', script()))
    page_ids = set().union(*(set(re.findall(r'\bid="([\w-]+)"', (STATIC / page).read_text())) for page in PAGES))
    assert ids and not ids - page_ids, ids - page_ids


def test_every_message_the_script_uses_exists_in_both_languages():
    source = script()
    table = source.split("const T = {")[1].split("\n};")[0]
    french, english = table.split("  en: {")
    known_fr, known_en = message_keys(french.split("fr: {")[1]), message_keys(english)
    used = set(re.findall(r'\bt\(\s*"(\w+)"', source))
    used |= {key for pair in re.findall(r'\bt\([^)"`]*\?\s*"(\w+)"\s*:\s*"(\w+)"', source) for key in pair}
    used |= {f"pii_{kind}" for kind in ("email", "phone", "iban", "card", "nir")}  # t(`pii_${kind}`) and t(`src_${kind}`)
    used |= {f"src_{kind}" for kind in ("ct", "gdpr", "none")}
    used |= {"wrong_answer", "wrong_citation", "missing_article", "other"}  # the kinds of the vote menu, written with t(k)
    assert len(used) > 30
    assert not used - known_fr, used - known_fr
    assert not used - known_en, used - known_en


def test_the_script_has_no_way_to_write_text_from_the_server_as_html():
    source = script()
    assert source.count(".innerHTML") == 2  # applyLanguage only: the French text of the page and the English text, both ours
    for sink in ("insertAdjacentHTML", "outerHTML", "document.write", "eval(", "new Function", "javascript:", "srcdoc"):
        assert sink not in source, sink


def test_every_fetch_of_the_script_goes_to_a_route_that_exists():
    urls = set(re.findall(r'fetch\("(/[\w-]+)"', script()))
    routes = {route.path for route in web.create_app(None, None).routes}
    assert urls == {"/ask", "/feedback", "/translate-answer", "/examples"} and urls <= routes


def test_every_internal_link_of_every_page_leads_to_a_page_that_exists():
    c = client()
    links = set()
    for page in PAGES:
        links |= set(re.findall(r'href="(/[^"#?]*)"', (STATIC / page).read_text()))
    assert {"/", "/method", "/data", "/privacy", "/history", "/static/style.css"} <= links
    for link in sorted(links):
        assert c.get(link).status_code == 200, link


def test_every_page_has_one_main_heading_a_language_a_viewport_and_the_scripts_in_order():
    for page in PAGES:
        html = (STATIC / page).read_text()
        assert html.count("<h1") == 1 and '<html lang="fr">' in html and 'name="viewport"' in html, page
        assert html.index("texts_en.js") < html.index("app.js"), page  # the English texts are defined before the script uses them
        for link in ('href="/"', 'href="/history"', 'href="/method"', 'href="/data"', 'href="/privacy"'):
            assert link in html or link == f'href="/{page.removesuffix(".html")}"', (page, link)  # a page need not link to itself


def test_the_translation_button_asks_for_a_translation_only_when_pressed():
    html, script = (STATIC / "index.html").read_text(), (STATIC / "app.js").read_text()
    assert 'id="translate"' in html and 'id="english"' in html and 'data-i18n="tr_button"' in html
    assert 'ask(question, true)' in script and "translate = false" in script  # the plain form never translates


def test_the_contact_address_is_not_written_in_any_page_or_script_but_the_pages_carry_the_parts_to_build_it():
    for page in PAGES:
        html = (STATIC / page).read_text()
        assert "labyrintbs@gmail.com" not in html and "mailto:" not in html, page
        assert 'class="mail"' in html and 'data-user="labyrintbs"' in html and 'data-host="gmail.com"' in html, page
        assert "Hongming Fang" in html and "linkedin.com/in/hongming-fang" in html, page  # the author line of the footer
    assert "labyrintbs@gmail.com" not in (STATIC / "app.js").read_text()


def test_the_pages_use_no_inline_script_or_style_that_the_policy_would_block():
    for page in PAGES:
        html = (STATIC / page).read_text()
        assert not re.search(r"<script(?![^>]*\bsrc=)", html) and "<style" not in html and " style=" not in html, page
        assert not re.search(r"\son\w+=", html), page


def english_keys() -> set[str]:
    block = (STATIC / "texts_en.js").read_text().split("const EN = {")[1].split("\n};")[0]
    return set(re.findall(r'(\w+): "', block))


def test_every_french_text_of_the_pages_has_an_english_one():
    english = english_keys()
    for page in PAGES:
        html = (STATIC / page).read_text()
        keys = set(re.findall(r'data-i18n(?:-placeholder|-content|-aria)?="(\w+)"', html))
        assert keys and not keys - english, (page, keys - english)


def message_keys(text: str) -> set[str]:
    """The keys of a table of messages: a name at the start of a line or after a comma, not a word before a colon in a text."""
    return set(re.findall(r'(?:^\s+|", )(\w+): "', text, re.MULTILINE))


def test_both_message_tables_hold_the_same_messages():
    source = (STATIC / "app.js").read_text()
    table = source.split("const T = {")[1].split("\n};")[0]
    french, english = table.split("  en: {")
    assert message_keys(french.split("fr: {")[1]) == message_keys(english) and len(message_keys(english)) > 20


def test_the_example_file_holds_real_dev_questions_with_both_labels():
    found = examples.load()
    dev = {q.question for q in gold.load_gold(ROOT / "eval/gold.jsonl") if q.split == "dev" and q.lang == "fr"}
    assert 4 <= len(found) <= 12
    assert all(e["source"] in examples.SOURCES and e["label"]["fr"] and e["label"]["en"] and e["question_en"] for e in found)
    not_dev = {e["question"] for e in found if e["question"] not in dev}
    assert not_dev == {  # the questions tried with the real model for the page (scripts/answers/stress_questions.py --only cards)
        "Un salarié démissionne : quel préavis doit-il respecter ?", "Quelle est la durée du préavis en cas de licenciement ?",
        "Comment fonctionne la rupture conventionnelle ?", "Que dit l'article L1221-13 du Code du travail ?",
        "Combien de temps peut-on conserver le CV d'un candidat qui n'a pas été retenu ?"}
    assert len({e["question"] for e in found}) == len(found)
    assert warm.load_questions(examples.EXAMPLES_FILE) == [e["question"] for e in found]


def test_an_example_entry_may_be_plain_text(tmp_path):
    path = tmp_path / "e.yaml"
    path.write_text("questions:\n  - Quelle durée ?\n")
    assert examples.load(path) == [{"question": "Quelle durée ?", "source": "none", "question_en": None,
                                    "label": {"fr": "Quelle durée ?", "en": "Quelle durée ?"}}]
