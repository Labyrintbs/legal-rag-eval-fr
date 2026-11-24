"""The page script (static/app.js with static/texts_en.js) run for real in a JavaScript engine (QuickJS), on a small fake page
and fake browser storage: the history, the drawing of replies, the translated-question line, the English button.
No browser is involved: what the fake page cannot show (the look) is for the eyes."""

import json
from pathlib import Path

import pytest

quickjs = pytest.importorskip("quickjs")

STATIC = Path(__file__).parents[2] / "src/legalrag/web/static"

HARNESS = r"""
class TextNode { constructor(text) { this.tag = "#text"; this.text = text; } }
class FakeNode {
  constructor(tag) {
    this.tag = tag; this.children = []; this.attrs = {}; this.dataset = {}; this.className = ""; this.hidden = false;
    this.disabled = false; this.value = ""; this.checked = false; this.listeners = {}; this.parent = null; this._inner = "";
  }
  setAttribute(name, value) {
    this.attrs[name] = String(value);
    if (name === "hidden") this.hidden = true;  // as in a browser, these attributes switch the property on
    if (name === "disabled") this.disabled = true;
  }
  getAttribute(name) { return this.attrs[name] === undefined ? null : this.attrs[name]; }
  _adopt(kids) {
    return kids.map((kid) => { const node = typeof kid === "string" ? new TextNode(kid) : kid; if (node.tag !== "#text") node.parent = this; return node; });
  }
  append(...kids) { this.children.push(...this._adopt(kids)); }
  prepend(...kids) { this.children.unshift(...this._adopt(kids)); }
  replaceChildren(...kids) { this.children = this._adopt(kids); }
  replaceWith(other) { const list = this.parent.children; list[list.indexOf(this)] = other; other.parent = this.parent; }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter((child) => child !== this); }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  click() { for (const fn of this.listeners.click || []) fn({ currentTarget: this, preventDefault() {} }); }
  fire(type) { for (const fn of this.listeners[type] || []) fn({ currentTarget: this, preventDefault() {} }); }
  focus() {}
  scrollIntoView() {}
  get textContent() { return this.children.map((child) => (child.tag === "#text" ? child.text : child.textContent)).join(""); }
  set textContent(value) { this.children = [new TextNode(String(value))]; }
  get innerHTML() { return this._inner; }
  set innerHTML(value) { this._inner = value; }
}
const registry = {};
const document = { documentElement: { lang: "fr" }, createElement: (tag) => new FakeNode(tag), getElementById: (id) => registry[id] || null,
  querySelectorAll: () => [] };
function makeStore(options = {}) {
  const data = {};
  return {
    data,
    getItem: (key) => { if (options.broken) throw new Error("denied"); return key in data ? data[key] : null; },
    setItem: (key, value) => { if (options.broken) throw new Error("denied"); data[key] = String(value); },
    removeItem: (key) => { if (options.broken) throw new Error("denied"); delete data[key]; },
  };
}
const window = { sessionStorage: makeStore(), localStorage: makeStore(), matchMedia: () => ({ matches: false }), location: { href: "" } };
const localStorage = window.localStorage;
function walk(node, out = []) { out.push(node); for (const child of node.children || []) walk(child, out); return out; }
function byClass(node, name) { return walk(node).filter((n) => (n.className || "").split(" ").includes(name)); }
function byTag(node, name) { return walk(node).filter((n) => n.tag === name); }
function pending() { return new Promise(() => {}); }
function toggles() { return byClass(registry.history, "hist").map((entry) => byTag(entry, "button")[0]); }  // show/hide of each entry
"""

CITATION = {"label": "L1221-19", "units": [4], "passage": "3° Pour les cadres, de quatre mois.",
            "section_path": "Partie > Livre > Titre", "url": "https://www.legifrance.gouv.fr/article"}
REPLY = {
    "request_id": "r" * 32, "outcome": "answered", "reason": None, "cached": False, "masked": [], "question_masked": None,
    "question_fr": None, "retry_after": None,
    "claims": [{"text": "Quatre mois pour un cadre.", "citations": [CITATION]},
               {"text": "Renouvelable une fois.", "citations": [{**CITATION, "units": [5], "passage": "Renouvelable."},
                                                                {"label": "art 17", "units": [1], "passage": "Droit à l'effacement.",
                                                                 "section_path": "Chapitre", "url": "https://eur-lex.europa.eu/x"}]}],
    "articles": [{"label": "L1221-19", "similarity": 0.6, "section_path": "A > B", "url": "https://www.legifrance.gouv.fr/article", "text": "texte"}],
}


@pytest.fixture
def page():
    ctx = quickjs.Context()
    ctx.eval(HARNESS)
    ctx.eval((STATIC / "texts_en.js").read_text())
    ctx.eval((STATIC / "app.js").read_text())
    return ctx


def run(ctx, code):
    """The value of a JavaScript expression (it must be JSON-able), after the promises it started have settled."""
    while ctx.execute_pending_job():
        pass
    value = ctx.eval("JSON.stringify(" + code + ")")
    return json.loads(value) if value is not None else None


def start(ctx, code):
    """Runs statements (a click that starts a request, for example) and lets the promises settle."""
    ctx.eval(code)
    while ctx.execute_pending_job():
        pass


def give(ctx, name, value):
    ctx.eval(f"globalThis.{name} = " + json.dumps(value))


# ---- the script itself ----

def test_the_script_and_the_english_texts_load_and_the_setup_runs_on_a_page_without_elements(page):
    assert run(page, "[typeof replyNode, typeof drawHistory, typeof looksEnglish, typeof EN.title, lang]") == ["function", "function", "function", "string", "fr"]


@pytest.mark.parametrize("text, english", [
    ("What is the notice period for a 1-year new employee?", True), ("Can my employer read my work emails?", True),
    ("How long is the probation period?", True), ("Quelle est la durée du préavis ?", False), ("Mon employeur peut-il me licencier ?", False),
    ("RGPD article 17", False), ("L1221-13", False), ("", False), ("préavis", False), ("the", False),
    ("Que dit l'article 17 of the RGPD ?", True),  # a mixed text: two English words against one French one: offered, harmlessly
    ("Est-ce que the employer peut le faire ?", False),
])
def test_the_script_takes_a_question_for_english_only_when_english_words_win(page, text, english):
    assert run(page, f"looksEnglish({json.dumps(text)})") is english


# ---- the history ----

def history_elements(page):
    """The elements of the history page that the script looks for."""
    for name in ("history", "keep", "clear", "confirm", "confirm-yes", "confirm-no"):
        page.eval(f'registry["{name}"] = new FakeNode("{"input" if name == "keep" else "section"}")')
    page.eval('registry.confirm.hidden = true')  # the page file starts with the question hidden


def test_the_history_keeps_the_answer_without_the_articles_once_per_request_and_stops_at_thirty(page):
    give(page, "reply", REPLY)
    start(page, 'addToHistory("Quelle durée pour un cadre ?", reply); addToHistory("Même question", reply)')
    entries = run(page, "readHistory()")
    assert len(entries) == 1 and entries[0]["question"] == "Même question"  # the same request: replaced, not repeated
    assert entries[0]["reply"]["articles"] == [] and entries[0]["reply"]["claims"][0]["text"] == "Quatre mois pour un cadre."
    start(page, 'for (let i = 0; i < 35; i++) addToHistory("Question " + i, { ...reply, request_id: "id" + i });')
    entries = run(page, "readHistory()")
    assert len(entries) == 30 and entries[0]["question"] == "Question 34" and entries[-1]["question"] == "Question 5"


def test_only_answers_and_refusals_are_kept_in_the_history(page):
    for outcome, kept in (("answered", 1), ("refused_by_model", 1), ("refused_weak_retrieval", 1), ("rate_limited", 0), ("llm_error", 0),
                          ("cache_hit", 0)):
        start(page, "clearHistory()")
        give(page, "reply", {**REPLY, "outcome": outcome})
        start(page, 'addToHistory("Q", reply)')
        assert len(run(page, "readHistory()")) == kept, outcome


def test_the_history_lives_in_the_tab_by_default_and_moves_to_the_device_only_when_asked(page):
    give(page, "reply", REPLY)
    start(page, 'addToHistory("Q", reply)')
    assert run(page, "[keepsHistory(), 'history' in window.sessionStorage.data, 'history' in window.localStorage.data]") == [False, True, False]
    start(page, "setKeepHistory(true)")
    assert run(page, "[keepsHistory(), 'history' in window.sessionStorage.data, 'history' in window.localStorage.data, readHistory().length]") == [True, False, True, 1]
    start(page, 'addToHistory("Q2", { ...reply, request_id: "other" })')
    assert run(page, "readHistory().length") == 2 and run(page, "'history' in window.sessionStorage.data") is False
    start(page, "setKeepHistory(false)")
    assert run(page, "[keepsHistory(), 'history' in window.sessionStorage.data, 'history' in window.localStorage.data, readHistory().length]") == [False, True, False, 2]


def test_erasing_the_history_empties_both_places(page):
    give(page, "reply", REPLY)
    start(page, 'addToHistory("Q", reply); setKeepHistory(true); addToHistory("Q2", { ...reply, request_id: "b" }); window.sessionStorage.setItem("history", "[1]")')
    start(page, "clearHistory()")
    assert run(page, "['history' in window.sessionStorage.data, 'history' in window.localStorage.data]") == [False, False]
    assert run(page, "readHistory()") == []


def test_a_refused_storage_a_full_one_or_a_damaged_history_never_breaks_the_page(page):
    give(page, "reply", REPLY)
    start(page, "window.sessionStorage = makeStore({ broken: true }); window.localStorage = makeStore({ broken: true })")
    start(page, 'addToHistory("Q", reply); setKeepHistory(true); setKeepHistory(false); clearHistory()')
    assert run(page, "[readHistory(), keepsHistory()]") == [[], False]
    start(page, "window.sessionStorage = makeStore(); window.localStorage = makeStore()")
    for damaged in ("{not json", '{"a": 1}', "null", '"text"', "[1, null, {}, {\\\"question\\\": 5, \\\"reply\\\": {}}]"):
        start(page, f"window.sessionStorage.data.history = '{damaged}'")
        assert run(page, "readHistory()") == [], damaged


def test_the_history_page_lists_the_entries_and_shows_a_stored_answer_without_vote_or_translation(page):
    history_elements(page)
    give(page, "reply", {**REPLY, "question_fr": "Quelle durée pour un cadre ?"})
    start(page, 'addToHistory("What is the probation period?", reply); addToHistory("Autre ?", { ...reply, request_id: "b", question_fr: null }); setupHistory()')
    assert run(page, "byClass(registry.history, 'hist').length") == 2
    assert run(page, "byClass(registry.history, 'hist')[1].children.filter((c) => c.tag === 'p')[0].children[0].text") == "What is the probation period?"
    start(page, "toggles()[1].click()")  # the newest entry is first: the translated one is the second
    assert run(page, "byClass(registry.history, 'hist-body')[1].hidden") is False
    assert run(page, "byClass(registry.history, 'hist-body')[0].hidden") is True  # the other stays closed
    shown = run(page, "walk(registry.history).filter((n) => n.tag === '#text').map((n) => n.text).join('|')")
    assert "Quatre mois pour un cadre." in shown and "Quelle durée pour un cadre ?" in shown  # the answer and the translated question
    assert run(page, "byClass(registry.history, 'vote').length + byClass(registry.history, 'en-answer').length") == 0
    start(page, "toggles()[1].click()")  # a second click hides it again
    assert run(page, "byClass(registry.history, 'hist-body')[1].hidden") is True


def history_page(page, *entries):
    """The history page with these (question, reply) entries, oldest first."""
    history_elements(page)
    give(page, "entries", [list(entry) for entry in entries])
    start(page, "for (const [q, r] of entries) addToHistory(q, r); setupHistory()")


def test_a_closed_entry_shows_its_status_and_the_french_question_and_a_refusal_is_not_called_an_answer(page):
    history_page(page, ("Probation?", {**REPLY, "question_fr": "Quelle période d'essai ?"}),
                 ("Hors sujet ?", {**REPLY, "request_id": "b", "outcome": "refused_by_model", "claims": []}),
                 ("Rien ?", {**REPLY, "request_id": "c", "outcome": "refused_weak_retrieval", "claims": []}))
    assert run(page, "byClass(registry.history, 'hist-status').map((n) => n.textContent)") == ["Sans réponse", "Sans réponse", "Répondu"]
    assert run(page, "byClass(registry.history, 'hist-fr').map((n) => n.textContent)") == ["Question traduite en français : Quelle période d'essai ?"]
    assert run(page, "toggles().map((b) => b.textContent)") == ["Afficher le résultat", "Afficher le résultat", "Afficher la réponse"]
    start(page, "toggles()[0].click()")
    assert run(page, "toggles()[0].textContent") == "Masquer le résultat"
    start(page, 'lang = "en"; drawHistory()')
    assert run(page, "byClass(registry.history, 'hist-status').map((n) => n.textContent)") == ["No answer", "No answer", "Answered"]
    assert run(page, "toggles().map((b) => b.textContent)") == ["Show the result", "Show the result", "Show the answer"]
    assert run(page, "byClass(registry.history, 'hist-fr')[0].textContent") == "Question translated into French: Quelle période d'essai ?"


def test_delete_removes_only_its_entry_and_edit_hands_the_old_question_to_the_first_page_through_the_tab_memory(page):
    history_page(page, ("Première ?", REPLY), ("Seconde ?", {**REPLY, "request_id": "b"}))
    assert run(page, "byClass(registry.history, 'hist').map((e) => byTag(e, 'button').map((b) => b.textContent))") == [
        ["Afficher la réponse", "Modifier cette question", "Supprimer cette entrée"]] * 2
    start(page, "byTag(byClass(registry.history, 'hist')[0], 'button')[2].click()")  # delete the newest
    assert run(page, "readHistory().map((e) => e.question)") == ["Première ?"]
    assert run(page, "byClass(registry.history, 'hist').length") == 1  # drawn again
    start(page, "byTag(byClass(registry.history, 'hist')[0], 'button')[1].click()")  # edit
    assert run(page, "[window.location.href, window.sessionStorage.data.prefill, readHistory().length]") == ["/", "Première ?", 1]  # nothing is sent, nothing removed
    start(page, "byTag(byClass(registry.history, 'hist')[0], 'button')[2].click()")
    assert run(page, "registry.history.textContent").startswith("Aucune question pour le moment.")


def test_erasing_the_history_asks_first_and_cancel_keeps_the_list_and_the_keep_box_stays_ticked(page):
    history_page(page, ("Q1 ?", REPLY), ("Q2 ?", {**REPLY, "request_id": "b"}))
    start(page, "setKeepHistory(true); registry.keep.checked = true")
    assert run(page, "registry.confirm.hidden") is True
    start(page, "registry.clear.click()")
    assert run(page, "[registry.confirm.hidden, readHistory().length]") == [False, 2]  # asked, nothing erased yet
    start(page, 'registry["confirm-no"].click()')
    assert run(page, "[registry.confirm.hidden, readHistory().length]") == [True, 2]
    start(page, 'registry.clear.click(); registry["confirm-yes"].click()')
    assert run(page, "[registry.confirm.hidden, readHistory().length, keepsHistory()]") == [True, 0, True]  # still ticked, as the page says


def test_a_browser_that_refuses_storage_gets_a_message_and_not_an_empty_list(page):
    page.eval('registry.history = new FakeNode("section")')
    start(page, "window.sessionStorage = makeStore({ broken: true }); drawHistory()")
    assert "ne permet pas de garder l'historique" in run(page, "registry.history.textContent")
    start(page, 'lang = "en"; drawHistory()')
    assert "does not allow keeping the history" in run(page, "registry.history.textContent")
    start(page, "window.sessionStorage = makeStore(); drawHistory()")
    assert "does not allow" not in run(page, "registry.history.textContent")


def test_an_opened_entry_gives_its_date_and_the_masking_notice_and_names_are_said_not_to_be_detected(page):
    history_page(page, ("Puis-je licencier Marie, marie@x.fr ?", {**REPLY, "masked": ["email"],
                                                                  "question_masked": "Puis-je licencier Marie, [e-mail] ?"}))
    start(page, "toggles()[0].click()")
    body = run(page, "byClass(registry.history, 'hist-body')[0].children.map((n) => n.className)")
    assert body == ["notice", "count", "answer"]  # notice, date line, answer
    text = run(page, "byClass(registry.history, 'hist-body')[0].textContent")
    assert "une adresse e-mail" in text and "Puis-je licencier Marie, [e-mail] ?" in text and "Donné le " in text and "la loi a pu changer" in text
    assert "Les noms et les adresses postales ne sont pas détectés" in text
    start(page, 'lang = "en"; drawHistory(); toggles()[0].click()')
    assert "Names and postal addresses are not detected" in run(page, "byClass(registry.history, 'hist-body')[0].textContent")
    give(page, "plain", {**REPLY, "request_id": "z"})
    start(page, 'addToHistory("Plain", plain); drawHistory(); toggles()[0].click()')
    assert run(page, "byClass(registry.history, 'hist-body')[0].children.map((n) => n.className)") == ["count", "answer"]  # no notice when nothing was masked


def test_the_first_page_takes_the_text_to_edit_once_and_fits_it_to_the_box(page):
    page.eval("""for (const name of ["ask", "question", "translate", "count", "english", "result"]) registry[name] = new FakeNode("div");
      registry.ask.requestSubmit = () => {}; fetch = async () => ({ json: async () => [] });""")
    start(page, 'window.sessionStorage.setItem("prefill", "x".repeat(600)); setup()')
    assert run(page, "registry.question.value.length") == 500 and run(page, "registry.count.textContent") == "500 / 500"
    assert run(page, "'prefill' in window.sessionStorage.data") is False  # taken once: a reload shows an empty box
    start(page, "registry.question.value = ''; setup()")
    assert run(page, "registry.question.value") == ""
    start(page, "window.sessionStorage = makeStore({ broken: true }); setup()")  # refused storage: an empty box, no error
    assert run(page, "registry.question.value") == ""


def test_the_history_page_says_so_when_it_is_empty_and_follows_the_language(page):
    page.eval('registry.history = new FakeNode("section")')
    start(page, "drawHistory()")
    assert run(page, "registry.history.textContent") == "Aucune question pour le moment. Cet onglet n'a pas de liste gardée : cochez la case ci-dessus pour garder la vôtre."
    start(page, 'lang = "en"; drawHistory()')
    assert run(page, "registry.history.textContent") == "No question yet. This tab has no kept list: tick the box above to keep yours."
    start(page, 'window.localStorage.setItem("keep_history", "1"); drawHistory()')  # a kept history has no such hint
    assert run(page, "registry.history.textContent") == "No question yet."


def test_ticking_the_keep_box_moves_the_history_and_unticking_moves_it_back(page):
    history_elements(page)
    give(page, "reply", REPLY)
    start(page, 'setupHistory(); addToHistory("Q", reply); registry.keep.checked = true; registry.keep.fire("change")')
    assert run(page, "[keepsHistory(), 'history' in window.localStorage.data]") == [True, True]
    start(page, 'registry.keep.checked = false; registry.keep.fire("change")')
    assert run(page, "[keepsHistory(), 'history' in window.localStorage.data, readHistory().length]") == [False, False, 1]
    start(page, 'registry.clear.click(); registry["confirm-yes"].click()')
    assert run(page, "readHistory()") == [] and run(page, "registry.history.textContent").startswith("Aucune question pour le moment.")


# ---- the drawing of a reply ----

def test_an_answer_is_one_paragraph_with_numbered_citations_one_tag_per_source_and_the_place_of_an_article_once(page):
    give(page, "reply", REPLY)
    assert run(page, "byTag(replyNode(reply, 200, null), 'sup').map((n) => n.textContent)") == ["1", "2", "3"]
    assert run(page, "byClass(replyNode(reply, 200, null), 'claim')[0].textContent") == "Quatre mois pour un cadre.1 Renouvelable une fois.23 "
    assert run(page, "byClass(replyNode(reply, 200, null), 'src').length") == 3
    assert run(page, "byClass(byClass(replyNode(reply, 200, null), 'sources')[0], 'tag').map((n) => n.className)") == ["tag ct", "tag gdpr"]
    assert run(page, "byClass(replyNode(reply, 200, null), 'src').map((n) => byClass(n, 'where').length)") == [2, 0, 1]
    assert run(page, "byClass(replyNode(reply, 200, null), 'vote').length") == 1


def test_an_answer_drawn_from_the_history_has_no_vote_translation_or_list_of_articles(page):
    give(page, "reply", {**REPLY, "question_fr": "Quelle durée ?"})
    assert run(page, "byClass(replyNode(reply, 200, null), 'en-answer').length") == 1  # the live answer offers it
    assert run(page, "byClass(replyNode(reply, 200, null, true), 'en-answer').length + byClass(replyNode(reply, 200, null, true), 'vote').length"
               " + byClass(replyNode(reply, 200, null, true), 'found').length") == 0


def test_text_from_the_server_is_never_turned_into_elements(page):
    attack = "<img src=x onerror=alert(1)><script>alert(2)</script>"
    give(page, "reply", {**REPLY, "reason": attack, "claims": [{"text": attack, "citations": [{**CITATION, "passage": attack, "label": attack,
                                                                                          "section_path": attack + " > " + attack}]}]})
    for outcome in ("answered", "refused_by_model"):
        page.eval(f'reply.outcome = "{outcome}"')
        assert run(page, "walk(replyNode(reply, 200, null)).filter((n) => ['img', 'script'].includes(n.tag)).length") == 0
        assert attack in run(page, "walk(replyNode(reply, 200, null)).filter((n) => n.tag === '#text').map((n) => n.text).join('|')")


def test_a_link_that_is_not_https_is_replaced_by_a_harmless_one(page):
    for url in ("javascript:alert(1)", "data:text/html,x", "HTTP://x", "//evil.example", " https://x", "vbscript:x", ""):
        give(page, "reply", {**REPLY, "claims": [{"text": "A.", "citations": [{**CITATION, "url": url}]}]})
        links = run(page, "byTag(byClass(replyNode(reply, 200, null), 'sources')[0], 'a').map((n) => n.attrs.href)")  # the cited passages
        assert links and all(link == "#" for link in links), (url, links)
    give(page, "reply", REPLY)
    assert run(page, "byTag(byClass(replyNode(reply, 200, null), 'sources')[0], 'a').map((n) => n.attrs.href)")[0].startswith("https://www.legifrance")


def test_a_refusal_says_what_the_service_covers_and_what_to_do_and_keeps_the_articles_closed(page):
    for outcome, first in (("refused_by_model", "Pas de réponse : les textes de ce service"), ("refused_weak_retrieval", "Pas de réponse : rien de suffisamment proche")):
        give(page, "reply", {**REPLY, "outcome": outcome, "claims": [], "reason": "Les extraits ne traitent pas du sujet."})
        text = run(page, "replyNode(reply, 200, null).textContent")
        assert first in text and "Code du travail et le RGPD" in text and "consultez un avocat" in text
        assert run(page, "byTag(replyNode(reply, 200, null), 'details').map((n) => n.attrs.open)") == [None]  # closed


@pytest.mark.parametrize("status, expected", [(0, "ne répond pas"), (422, "entre 1 et 500"), (429, "Réessayez dans 12 s"), (503, "indisponible"), (502, "modèle n'a pas répondu")])
def test_an_error_status_is_told_in_words(page, status, expected):
    give(page, "reply", {**REPLY, "outcome": "rate_limited", "claims": [], "articles": []})
    assert expected in run(page, f"replyNode(reply, {status}, 12).textContent")


def test_the_page_follows_the_language_for_the_messages_it_builds(page):
    give(page, "reply", REPLY)
    start(page, 'lang = "en"')
    assert "Answer (in French)" in run(page, "replyNode(reply, 200, null).textContent") and "Cited passages" in run(page, "replyNode(reply, 200, null).textContent")
    assert "Too many requests from you. Try again in 9 s." in run(page, "replyNode(reply, 429, 9).textContent")


# ---- notices of the result area ----

def test_the_result_shows_the_masking_notice_then_the_translated_question_then_the_answer(page):
    page.eval('registry.result = new FakeNode("section")')
    give(page, "shown", {"reply": {**REPLY, "masked": ["email", "phone"], "question_masked": "Quelle durée ? [e-mail] [téléphone]",
                                   "question_fr": "Quelle durée ?"}, "status": 200, "retryAfter": None})
    start(page, "last = shown; show()")  # `last` is a variable of the script, not a global property
    assert run(page, "registry.result.children.map((n) => n.className)") == ["notice", "tr-line", "answer"]
    notice = run(page, "registry.result.children[0].textContent")
    assert "une adresse e-mail, un numéro de téléphone" in notice and "Quelle durée ? [e-mail] [téléphone]" in notice


def test_the_translated_question_is_plain_text_until_modifier_is_pressed_then_a_field_with_a_button_that_waits_for_a_change(page):
    give(page, "reply", {**REPLY, "question_fr": "Quelle durée pour un directeur ?"})
    start(page, "globalThis.box = translatedLine(reply); globalThis.asked = []; ask = (...args) => { asked.push(args); }")
    assert run(page, "[byTag(box, 'q').length, byTag(box, 'textarea').length, byClass(box, 'linklike').length]") == [1, 0, 1]
    assert run(page, "byTag(box, 'q')[0].textContent") == "Quelle durée pour un directeur ?"
    start(page, "byClass(box, 'linklike')[0].click()")
    assert run(page, "[byTag(box, 'q').length, byTag(box, 'textarea').length, byClass(box, 'send')[0].disabled]") == [0, 1, True]
    assert run(page, "byTag(box, 'textarea')[0].value") == "Quelle durée pour un directeur ?"  # the text to correct
    start(page, "byTag(box, 'textarea')[0].fire('input')")
    assert run(page, "byClass(box, 'send')[0].disabled") is True  # unchanged: nothing to ask again
    start(page, "byTag(box, 'textarea')[0].value = '   '; byTag(box, 'textarea')[0].fire('input')")
    assert run(page, "byClass(box, 'send')[0].disabled") is True  # blank
    start(page, "byTag(box, 'textarea')[0].value = '  Quelle durée pour un cadre ?  '; byTag(box, 'textarea')[0].fire('input')")
    assert run(page, "byClass(box, 'send')[0].disabled") is False
    start(page, "byClass(box, 'send')[0].click()")
    assert run(page, "asked") == [["Quelle durée pour un cadre ?", False, True]]  # trimmed, not translated again, from the field


def test_the_translation_of_the_answer_is_offered_only_to_a_visitor_who_asked_in_english_or_reads_english(page):
    give(page, "reply", REPLY)
    assert run(page, "englishBlock(reply)") == ""  # a French visitor: nothing
    give(page, "reply", {**REPLY, "question_fr": "Quelle durée ?"})
    assert run(page, "byTag(englishBlock(reply), 'button').length") == 1
    give(page, "reply", {**REPLY, "outcome": "refused_by_model", "question_fr": "Quelle durée ?"})
    assert run(page, "englishBlock(reply)") == ""  # a refusal has nothing to translate
    give(page, "reply", REPLY)
    start(page, 'lang = "en"')
    assert run(page, "byTag(englishBlock(reply), 'button').length") == 1


def fake_fetch(page, status, body, retry_after=None):
    give(page, "fetchCall", {"status": status, "body": body, "retry": retry_after})
    page.eval("""globalThis.requests = [];
      fetch = async (url, options) => { requests.push([url, JSON.parse(options.body)]);
        return { status: fetchCall.status, headers: { get: () => fetchCall.retry }, json: async () => fetchCall.body }; };""")


def test_pressing_the_english_button_sends_only_the_request_id_and_shows_the_translation_with_its_numbers(page):
    give(page, "reply", {**REPLY, "question_fr": "Quelle durée ?"})
    fake_fetch(page, 200, {"english": "Four months for an executive (cadre). [1] It may be renewed. [2]"})
    start(page, "globalThis.box = englishBlock(reply); byTag(box, 'button')[0].click()")
    assert run(page, "requests") == [["/translate-answer", {"request_id": "r" * 32}]]  # nothing else is sent
    assert run(page, "byTag(box, 'sup').map((n) => n.textContent)") == ["1", "2"]
    assert "Four months for an executive (cadre)." in run(page, "box.textContent") and "French text is authoritative" in run(page, "box.textContent")
    assert run(page, "byTag(box, 'button').length") == 0


@pytest.mark.parametrize("status, retry, expected", [(429, "7", "Réessayez dans 7 s"), (502, None, "n'a pas pu être faite"), (410, None, "n'a pas pu être faite"),
                                                      (503, None, "n'a pas pu être faite")])
def test_a_translation_that_fails_says_so_and_lets_the_visitor_try_again(page, status, retry, expected):
    give(page, "reply", {**REPLY, "question_fr": "Quelle durée ?"})
    fake_fetch(page, status, {"detail": "x"}, retry)
    start(page, "globalThis.box = englishBlock(reply); byTag(box, 'button')[0].click()")
    assert expected in run(page, "box.textContent")
    assert run(page, "byTag(box, 'button')[0].disabled") is False  # the button is back


def test_a_translation_request_that_cannot_reach_the_service_is_a_message_and_not_an_error(page):
    give(page, "reply", {**REPLY, "question_fr": "Quelle durée ?"})
    page.eval('fetch = async () => { throw new Error("network down"); }')
    start(page, "globalThis.box = englishBlock(reply); byTag(box, 'button')[0].click()")
    assert "n'a pas pu être faite" in run(page, "box.textContent") and run(page, "byTag(box, 'button')[0].disabled") is False


def test_a_translation_asked_for_is_kept_in_its_history_entry_and_shown_there_without_a_new_request(page):
    page.eval('registry.history = new FakeNode("section")')
    give(page, "reply", {**REPLY, "question_fr": "Quelle durée ?"})
    start(page, 'addToHistory("How long?", reply); addToHistory("Other", { ...reply, request_id: "b" })')
    fake_fetch(page, 200, {"english": "Four months. [1]"})
    start(page, "globalThis.box = englishBlock(reply); byTag(box, 'button')[0].click()")
    english = run(page, "readHistory().map((e) => e.reply.english)")
    assert english == [None, "Four months. [1]"]  # only the entry of this answer (newest first: "Other" is first)
    start(page, "drawHistory(); toggles()[1].click()")  # open the entry that has the translation
    assert run(page, "byClass(registry.history, 'en-answer').length") == 1
    assert "Four months." in run(page, "byClass(registry.history, 'en-answer')[0].textContent")
    assert run(page, "byClass(registry.history, 'en-answer')[0].textContent").startswith("Machine translation")
    assert run(page, "requests.length") == 1  # the history made no request
    assert run(page, "byTag(registry.history, 'button').filter((b) => b.className === 'pill' && b.textContent.includes('English')).length") == 0


def test_a_translation_of_an_answer_that_is_not_in_the_history_is_shown_and_nothing_breaks(page):
    give(page, "reply", {**REPLY, "question_fr": "Quelle durée ?"})
    fake_fetch(page, 200, {"english": "Four months. [1]"})
    start(page, "globalThis.box = englishBlock(reply); byTag(box, 'button')[0].click()")  # a 429 or a refused entry was never kept
    assert "Four months." in run(page, "box.textContent") and run(page, "readHistory()") == []


def test_the_ready_made_badge_is_shown_on_the_live_answer_and_not_kept_in_the_history(page):
    give(page, "reply", {**REPLY, "cached": True})
    assert run(page, "byClass(replyNode(reply, 200, null), 'badge').length") == 1
    start(page, 'addToHistory("Q", reply)')
    assert "cached" not in run(page, "readHistory()[0].reply")
    give(page, "old", {**REPLY, "cached": True})  # an entry kept by an earlier version of the page
    assert run(page, "byClass(replyNode(old, 200, null, true), 'badge').length") == 0


def test_a_date_is_written_with_the_month_as_a_word_without_seconds_in_both_languages(page):
    start(page, "globalThis.iso = new Date(2026, 10, 24, 9, 5, 33).toISOString()")  # local time, so the test does not depend on the zone
    assert run(page, "formatDate(iso)") == "24 nov. 2026, 09:05"
    start(page, 'lang = "en"')
    assert run(page, "formatDate(iso)") == "24 Nov 2026, 09:05"
    assert run(page, "formatDate('not a date')") == ""


def test_the_citation_numbers_of_a_translation_become_small_tags_and_other_brackets_stay_text(page):
    start(page, 'globalThis.p = withMarkers("A. [1] B [2][3] C [x] [10] (see [4)")')
    assert run(page, "byTag(p, 'sup').map((n) => n.textContent)") == ["1", "2", "3", "10"]
    assert run(page, "p.textContent") == "A. 1 B 23 C [x] 10 (see [4)"


# ---- asking ----

def test_a_question_is_sent_with_the_translate_flag_and_a_good_answer_enters_the_history(page):
    for name in ("go", "result"):
        page.eval(f'registry.{name} = new FakeNode("{"button" if name == "go" else "section"}")')
    fake_fetch(page, 200, REPLY)
    start(page, 'ask("How long?", true)')
    assert run(page, "requests") == [["/ask", {"question": "How long?", "translate": True}]]
    assert run(page, "readHistory().map((e) => e.question)") == ["How long?"]
    assert run(page, "registry.go.disabled") is False and run(page, "byClass(registry.result, 'answer').length") == 1
    fake_fetch(page, 429, {**REPLY, "outcome": "rate_limited", "claims": []}, "5")
    start(page, 'ask("Encore ?")')
    assert run(page, "readHistory().length") == 1  # a refusal for the limit is not kept
    assert "Réessayez dans 5 s" in run(page, "registry.result.textContent")


def test_a_question_asked_from_the_translated_field_keeps_that_french_text_on_screen(page):
    for name in ("go", "result"):
        page.eval(f'registry.{name} = new FakeNode("{"button" if name == "go" else "section"}")')
    fake_fetch(page, 200, REPLY)
    start(page, 'ask("Quelle durée pour un cadre ?", false, true)')
    assert run(page, "last.reply.question_fr") == "Quelle durée pour un cadre ?"
    assert run(page, "byClass(registry.result, 'tr-line').length") == 1


def test_a_rejected_question_shows_the_message_and_not_the_body_of_the_error(page):
    for name in ("go", "result"):
        page.eval(f'registry.{name} = new FakeNode("{"button" if name == "go" else "section"}")')
    fake_fetch(page, 422, {"detail": [{"loc": ["body", "question"], "msg": "secret detail", "type": "x"}]})
    start(page, 'ask("x")')
    text = run(page, "registry.result.textContent")
    assert "entre 1 et 500" in text and "secret detail" not in text


def test_every_english_text_the_page_swaps_in_is_a_string_and_the_two_message_tables_agree_at_run_time(page):
    assert run(page, "Object.keys(EN).filter((key) => typeof EN[key] !== 'string')") == []
    assert run(page, "Object.keys(T.fr).filter((key) => !(key in T.en)).concat(Object.keys(T.en).filter((key) => !(key in T.fr)))") == []
    assert run(page, "Object.keys(T.fr).filter((key) => /\\{(\\w+)\\}/.test(T.fr[key]) !== /\\{(\\w+)\\}/.test(T.en[key]))") == []  # the same placeholders
