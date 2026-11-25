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
  replaceChildren(...kids) {
    for (const child of this.children) if (child.tag !== "#text") child.parent = null;  // removed nodes are no longer part of the page
    this.children = this._adopt(kids);
  }
  after(other) { const list = this.parent.children; list.splice(list.indexOf(this) + 1, 0, other); other.parent = this.parent; }
  replaceWith(other) { const list = this.parent.children; list[list.indexOf(this)] = other; other.parent = this.parent; this.parent = null; }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter((child) => child !== this); }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  click() { for (const fn of this.listeners.click || []) fn({ currentTarget: this, preventDefault() {} }); }
  fire(type) { for (const fn of this.listeners[type] || []) fn({ currentTarget: this, preventDefault() {} }); }
  focus() { document.activeElement = this; }
  get isConnected() { let node = this; while (node.parent) node = node.parent; return Object.values(registry).includes(node); }
  scrollIntoView() {}
  get textContent() { return this.children.map((child) => (child.tag === "#text" ? child.text : child.textContent)).join(""); }
  set textContent(value) { this.children = [new TextNode(String(value))]; }
  get innerHTML() { return this._inner; }
  set innerHTML(value) { this._inner = value; }
}
const registry = {};
const document = { activeElement: null, addEventListener() {}, documentElement: { lang: "fr" }, createElement: (tag) => new FakeNode(tag), getElementById: (id) => registry[id] || null,
  querySelectorAll: () => [] };
function makeStore(options = {}) {
  const data = {};
  return {
    data,
    getItem: (key) => { if (options.broken || (options.failGet || []).includes(key)) throw new Error("denied"); return key in data ? data[key] : null; },
    setItem: (key, value) => {  // full: reads still work; failSet and failRemove name the keys that refuse
      if (options.broken || options.full || (options.failSet || []).includes(key)) throw new Error("denied");
      data[key] = String(value);
    },
    removeItem: (key) => { if (options.broken || (options.failRemove || []).includes(key)) throw new Error("denied"); delete data[key]; },
  };
}
const window = { sessionStorage: makeStore(), localStorage: makeStore(), matchMedia: () => ({ matches: false }), location: { href: "" },
  handlers: {}, addEventListener(type, fn) { (this.handlers[type] = this.handlers[type] || []).push(fn); },
  fire(type, event = {}) { for (const fn of this.handlers[type] || []) fn(event); } };
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


def click_mail(page):
    """Click a fresh contact link; the timer is replaced by a list the test runs by hand."""
    run(page, """(() => {
      const box = new FakeNode("p"), link = new FakeNode("a");
      link.dataset = { user: "me", host: "example.org" }; box.append(link); globalThis.link = link;
      globalThis.timers = []; globalThis.setTimeout = (fn, ms, ...args) => timers.push(() => fn(...args));
      openMail({ currentTarget: link, preventDefault() {} }); return 1; })()""")


def test_the_contact_link_opens_the_mail_program_and_shows_no_address_when_the_page_lost_focus(page):
    click_mail(page)
    run(page, "(noteFocusLoss(), timers.forEach((fn) => fn()), 1)")  # the mail program took the focus
    assert run(page, "[window.location.href, link.parent.textContent]") == ["mailto:me@example.org", ""]


def test_the_contact_link_shows_the_address_once_when_the_page_kept_focus(page):
    click_mail(page)
    run(page, "(lastFocusLoss = 0, timers.forEach((fn) => fn()), timers.forEach((fn) => fn()), 1)")
    assert run(page, "link.parent.textContent") == " (me@example.org)"


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
    for name in ("history", "keep", "clear", "confirm", "confirm-yes", "confirm-no", "keep-failed", "unkeep-failed", "erase-failed"):
        page.eval(f'registry["{name}"] = new FakeNode("{"input" if name == "keep" else "section"}")')
    page.eval('for (const name of ["confirm", "keep-failed", "unkeep-failed", "erase-failed"]) registry[name].hidden = true')  # hidden in the page file


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


def test_the_history_page_lists_the_entries_and_shows_a_stored_answer_without_a_vote(page):
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
    assert run(page, "byClass(registry.history, 'vote').length") == 0
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
    assert run(page, "toggles().map((b) => b.textContent)") == ["Hide the result", "Show the result", "Show the answer"]  # the opened one stays open
    assert run(page, "byClass(registry.history, 'hist-fr')[0].textContent") == "Question translated into French: Quelle période d'essai ?"


def test_delete_removes_only_its_entry_and_edit_hands_the_old_question_to_the_first_page_through_the_tab_memory(page):
    history_page(page, ("Première ?", REPLY), ("Seconde ?", {**REPLY, "request_id": "b"}))
    assert run(page, "byClass(registry.history, 'hist').map((e) => byTag(e, 'button').map((b) => b.textContent))") == [
        ["Afficher la réponse", "Modifier cette question", "Supprimer cette entrée"]] * 2
    start(page, "lastDeleteAt = 0; byTag(byClass(registry.history, 'hist')[0], 'button')[2].click()")  # delete the newest
    assert run(page, "readHistory().map((e) => e.question)") == ["Première ?"]
    assert run(page, "byClass(registry.history, 'hist').length") == 1  # drawn again
    start(page, "byTag(byClass(registry.history, 'hist')[0], 'button')[1].click()")  # edit
    assert run(page, "[window.location.href, window.sessionStorage.data.prefill, readHistory().length]") == ["/", "Première ?", 1]  # nothing is sent, nothing removed
    start(page, "lastDeleteAt = 0; byTag(byClass(registry.history, 'hist')[0], 'button')[2].click()")
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
    assert "une adresse e-mail" in text and "Puis-je licencier Marie, [e-mail] ?" in text and "Réponse du " in text and "la loi a pu changer" in text
    assert "Les noms et les adresses postales ne sont pas détectés" in text
    start(page, 'lang = "en"; drawHistory(); toggles()[0].click()')
    assert "Names and postal addresses are not detected" in run(page, "byClass(registry.history, 'hist-body')[0].textContent")
    give(page, "plain", {**REPLY, "request_id": "z"})
    start(page, 'addToHistory("Plain", plain); drawHistory(); toggles()[0].click()')
    assert run(page, "byClass(registry.history, 'hist-body')[0].children.map((n) => n.className)") == ["count", "answer"]  # no notice when nothing was masked


def test_a_change_of_language_keeps_the_opened_entries_open_and_a_deleted_one_is_forgotten(page):
    history_page(page, ("Première ?", REPLY), ("Seconde ?", {**REPLY, "request_id": "b"}))
    start(page, "toggles()[1].click()")  # open the older one
    assert run(page, "byClass(registry.history, 'hist-body').map((n) => n.hidden)") == [True, False]
    start(page, 'lang = "en"; drawHistory()')
    assert run(page, "byClass(registry.history, 'hist-body').map((n) => n.hidden)") == [True, False]
    assert run(page, "toggles().map((b) => b.textContent)") == ["Show the answer", "Hide the answer"]
    assert "Answer given on" in run(page, "byClass(registry.history, 'hist-body')[1].textContent")  # written in the new language
    start(page, "toggles()[1].click(); drawHistory()")  # closed by the visitor: stays closed
    assert run(page, "byClass(registry.history, 'hist-body').map((n) => n.hidden)") == [True, True]
    start(page, "toggles()[0].click(); byTag(byClass(registry.history, 'hist')[0], 'button')[2].click()")  # open then delete
    assert run(page, "openEntries.size") == 0


def test_the_reasons_of_the_service_are_french_so_the_english_page_does_not_repeat_them_and_labels_the_model_reason(page):
    give(page, "limited", {**REPLY, "outcome": "rate_limited", "claims": [], "reason": "une autre question est déjà en cours pour vous"})
    assert "déjà en cours" in run(page, "replyNode(limited, 429, 2).textContent")
    start(page, 'lang = "en"')
    text = run(page, "replyNode(limited, 429, 2).textContent")
    assert "déjà en cours" not in text and "Try again in 2 seconds" in text
    give(page, "refused", {**REPLY, "outcome": "refused_by_model", "claims": [], "reason": "Aucun texte ne traite de ce sujet."})
    text = run(page, "replyNode(refused, 200, null).textContent")
    assert "Reason given by the service (in French): Aucun texte ne traite de ce sujet." in text


def result_area(page):
    for name in ("go", "result"):
        page.eval(f'registry.{name} = new FakeNode("{"button" if name == "go" else "section"}")')


def test_the_masking_notice_is_shown_only_for_a_reply_that_used_the_question(page):
    result_area(page)
    masked = {**REPLY, "masked": ["email"], "question_masked": "Quelle durée ? [e-mail]", "outcome": "rate_limited", "claims": []}
    fake_fetch(page, 429, masked, "5")
    start(page, 'ask("Quelle durée ? a@b.fr")')
    assert run(page, "byClass(registry.result, 'notice').length") == 0 and "Réessayez dans 5 s" in run(page, "registry.result.textContent")
    fake_fetch(page, 200, {**REPLY, "masked": ["email"], "question_masked": "Quelle durée ? [e-mail]"})
    start(page, 'ask("Quelle durée ? a@b.fr")')
    assert run(page, "byClass(registry.result, 'notice').length") == 1


def test_a_busy_reply_has_its_own_message_in_both_languages_and_no_french_reason_on_the_english_page(page):
    give(page, "busy", {**REPLY, "outcome": "rate_limited", "claims": [], "articles": [], "busy": True, "retry_after": 2,
                        "reason": "une autre question est déjà en cours depuis votre connexion : attendez sa réponse"})
    assert run(page, "replyNode(busy, 429, 2).textContent") == "Une autre question est déjà en cours depuis votre connexion : attendez sa réponse."
    start(page, 'lang = "en"')
    assert run(page, "replyNode(busy, 429, 2).textContent") == "Another question is already in progress from your connection: wait for its answer."


def test_the_visitor_is_told_when_the_history_could_not_keep_the_answer_and_not_otherwise(page):
    result_area(page)
    fake_fetch(page, 200, REPLY)
    start(page, 'ask("Q ?")')
    assert "n'a pas pu être gardée" not in run(page, "registry.result.textContent")
    start(page, "window.sessionStorage = makeStore({ broken: true })")
    fake_fetch(page, 200, {**REPLY, "request_id": "b"})
    start(page, 'ask("Q2 ?")')
    assert "n'a pas pu être gardée dans l'historique" in run(page, "registry.result.textContent")
    fake_fetch(page, 200, {**REPLY, "request_id": "c", "outcome": "cache_hit"})  # nothing to keep is not a failure
    start(page, 'ask("Q3 ?")')
    assert "n'a pas pu être gardée" not in run(page, "registry.result.textContent")


def test_a_translation_already_asked_for_is_shown_again_after_a_change_of_language_without_a_new_request(page):
    result_area(page)
    fake_fetch(page, 200, {**REPLY, "question_fr": "Quelle durée ?"})
    start(page, 'ask("How long?", true)')
    fake_fetch(page, 200, {"english": "Four months. [1]"})
    start(page, "byTag(registry.result, 'button').filter((b) => b.className === 'pill')[0].click()")
    assert run(page, "last.reply.english") == "Four months. [1]" and run(page, "requests.length") == 1
    start(page, 'lang = "en"; show()')  # the page is drawn again
    assert run(page, "byClass(registry.result, 'en-answer')[0].textContent").endswith("Four months. 1")
    assert run(page, "byClass(registry.result, 'en-answer')[0].children.filter((c) => c.tag === 'button').length") == 0
    assert run(page, "requests.length") == 1


def test_the_date_line_of_an_opened_entry_says_answer_or_result_in_both_languages(page):
    history_page(page, ("A ?", REPLY), ("B ?", {**REPLY, "request_id": "b", "outcome": "refused_by_model", "claims": []}))
    start(page, "toggles()[0].click(); toggles()[1].click()")  # newest first: the refusal, then the answer
    dated = "byClass(registry.history, 'hist-body').map((b) => b.children.filter((c) => c.className === 'count')[0].textContent.split(' ').slice(0, 2).join(' '))"
    assert run(page, dated) == ["Résultat du", "Réponse du"]
    start(page, 'lang = "en"; drawHistory()')
    assert run(page, dated) == ["Result given", "Answer given"]


def test_the_english_headings_say_that_the_passages_and_articles_are_in_french(page):
    start(page, 'lang = "en"')
    assert run(page, "[t('cited'), t('found', { n: 5 }), t('found_weak', { n: 5 })]") == [
        "Cited passages (in French)", "The 5 articles closest to your question (in French)", "The 5 closest articles (not very relevant here; in French)"]


def test_every_button_of_an_entry_says_which_question_it_is_for_and_the_show_button_tells_if_it_is_open(page):
    long = "Quelle est la durée de la période d'essai pour un cadre embauché en CDI ?"
    history_page(page, (long, REPLY), ("Courte ?", {**REPLY, "request_id": "b"}))
    labels = run(page, "byClass(registry.history, 'hist').map((e) => byTag(e, 'button').map((b) => b.getAttribute('aria-label')))")
    assert labels[1] == ["Afficher la réponse : " + long[:40] + "…", "Modifier cette question : " + long[:40] + "…",
                         "Supprimer cette entrée : " + long[:40] + "…"]
    assert labels[0][0] == "Afficher la réponse : Courte ?"  # a short question is not cut
    assert run(page, "toggles().map((b) => b.getAttribute('aria-expanded'))") == ["false", "false"]
    start(page, "toggles()[0].click()")
    assert run(page, "toggles()[0].getAttribute('aria-expanded')") == "true"
    assert run(page, "toggles()[0].getAttribute('aria-label')") == "Masquer la réponse : Courte ?"
    start(page, 'lang = "en"; drawHistory()')  # drawn again, still open
    assert run(page, "[toggles()[0].getAttribute('aria-expanded'), toggles()[0].getAttribute('aria-label')]") == ["true", "Hide the answer: Courte ?"]


def test_after_a_delete_the_focus_goes_to_the_entry_now_at_that_place_then_to_the_last_then_to_the_tick_box(page):
    history_page(page, ("A ?", REPLY), ("B ?", {**REPLY, "request_id": "b"}), ("C ?", {**REPLY, "request_id": "c"}))  # shown: C, B, A
    start(page, "lastDeleteAt = 0; byTag(byClass(registry.history, 'hist')[0], 'button')[2].click()")  # delete C: B is now first
    assert run(page, "document.activeElement === toggles()[0] && readHistory().map((e) => e.question).join()") == "B ?,A ?"
    start(page, "lastDeleteAt = 0; byTag(byClass(registry.history, 'hist')[1], 'button')[2].click()")  # delete the last one (A)
    assert run(page, "document.activeElement === toggles()[0]") is True  # the last remaining
    start(page, "lastDeleteAt = 0; byTag(byClass(registry.history, 'hist')[0], 'button')[2].click()")  # delete the only one
    assert run(page, "document.activeElement === registry.keep") is True


def test_the_erase_question_takes_the_focus_on_cancel_gives_it_back_and_is_not_asked_for_an_empty_list(page):
    history_page(page)
    start(page, "registry.clear.click()")
    assert run(page, "registry.confirm.hidden") is True  # nothing to erase
    history_page(page, ("A ?", REPLY))
    start(page, "registry.clear.click()")
    assert run(page, "[registry.confirm.hidden, document.activeElement === registry['confirm-no']]") == [False, True]
    start(page, 'registry["confirm-no"].click()')
    assert run(page, "[registry.confirm.hidden, document.activeElement === registry.clear]") == [True, True]
    start(page, 'registry.clear.click(); registry["confirm-yes"].click()')
    assert run(page, "[registry.confirm.hidden, readHistory().length, document.activeElement === registry.clear]") == [True, 0, True]


def test_edit_this_question_offers_the_translation_again_only_for_a_question_that_was_translated(page):
    history_page(page, ("Probation period?", {**REPLY, "question_fr": "Quelle période d'essai ?"}), ("Quelle durée ?", {**REPLY, "request_id": "b"}))
    start(page, "byTag(byClass(registry.history, 'hist')[1], 'button')[1].click()")  # the English one
    assert run(page, "[window.sessionStorage.data.prefill, window.sessionStorage.data.prefill_english, window.location.href]") == ["Probation period?", "1", "/"]
    page.eval("""for (const name of ["ask", "question", "translate", "count", "english", "result"]) registry[name] = new FakeNode("div");
      registry.ask.requestSubmit = () => {}; fetch = async () => ({ json: async () => [] }); registry.english.hidden = true;""")
    start(page, "setup()")  # the first page
    assert run(page, "registry.question.value") == "Probation period?"
    assert run(page, "registry.english.hidden") is False  # "Probation period?" alone would not look English to the script
    start(page, "byTag(byClass(registry.history, 'hist')[0], 'button')[1].click(); registry.english.hidden = true; setup()")
    assert run(page, "registry.question.value") == "Quelle durée ?" and run(page, "registry.english.hidden") is True


def test_asking_again_from_the_french_line_keeps_the_english_question_and_replaces_the_first_entry(page):
    result_area(page)
    fake_fetch(page, 200, {**REPLY, "question_fr": "Quelle période d'essai ?"})
    start(page, 'ask("Probation period?", true)')
    fake_fetch(page, 200, {**REPLY, "request_id": "second"})
    start(page, 'ask("Quelle période d\'essai pour un cadre ?", false, true)')  # the corrected French line
    entries = run(page, "readHistory()")
    assert [(e["id"], e["question"]) for e in entries] == [("second", "Probation period?")]  # one entry, the English kept
    assert entries[0]["reply"]["question_fr"] == "Quelle période d'essai pour un cadre ?"
    start(page, 'ask("Quelle période d\'essai pour un directeur ?", false, true)')  # and again
    assert run(page, "readHistory().map((e) => e.question)") == ["Probation period?"]
    fake_fetch(page, 200, {**REPLY, "request_id": "third"})
    start(page, 'ask("Autre question ?")')  # a new question starts a new entry
    assert run(page, "readHistory().length") == 2


def test_another_tab_that_changes_the_kept_list_is_shown_here_and_a_write_never_uses_an_old_copy_of_the_list(page):
    history_page(page)
    give(page, "reply", REPLY)
    start(page, 'setKeepHistory(true); registry.keep.checked = true; addToHistory("From this tab", reply)')
    # another tab adds an entry straight into the shared storage of the device
    start(page, """const list = JSON.parse(window.localStorage.data.history);
      list.unshift({ id: "other", at: new Date().toISOString(), question: "From another tab", reply: { ...list[0].reply, request_id: "other" } });
      window.localStorage.data.history = JSON.stringify(list);""")
    assert run(page, "byClass(registry.history, 'hist').length") == 0  # the first drawing is old: this tab has not been told yet
    start(page, 'window.fire("storage")')  # the browser tells this tab
    assert run(page, "byClass(registry.history, 'hist').length") == 2
    start(page, 'addToHistory("Newest from this tab", { ...reply, request_id: "third" })')  # the write re-reads: nothing of the other tab is lost
    assert run(page, "readHistory().map((e) => e.question)") == ["Newest from this tab", "From another tab", "From this tab"]
    start(page, 'registry.keep.checked = false; window.localStorage.data.keep_history = "1"; window.fire("storage")')
    assert run(page, "registry.keep.checked") is True  # the tick follows the other tab


def test_ticking_keep_never_loses_the_list_when_the_device_storage_refuses_or_is_full(page):
    history_page(page, ("A ?", REPLY), ("B ?", {**REPLY, "request_id": "b"}))
    for options in ("{ broken: true }", "{ full: true }"):
        start(page, f"window.localStorage = makeStore({options}); registry.keep.checked = true; registry.keep.fire('change')")
        assert run(page, "[readHistory().length, keepsHistory(), registry.keep.checked, registry['keep-failed'].hidden]") == [2, False, False, False], options
        assert run(page, "'history' in window.sessionStorage.data") is True  # still in the tab
        assert run(page, "byClass(registry.history, 'hist').length") == 2
    start(page, "window.localStorage = makeStore(); registry.keep.checked = true; registry.keep.fire('change')")  # the device works again
    assert run(page, "[readHistory().length, keepsHistory(), registry.keep.checked, registry['keep-failed'].hidden]") == [2, True, True, True]
    assert run(page, "['history' in window.sessionStorage.data, 'history' in window.localStorage.data]") == [False, True]


def test_unticking_keep_never_loses_the_list_when_the_tab_storage_refuses(page):
    history_page(page, ("A ?", REPLY))
    start(page, "setKeepHistory(true); registry.keep.checked = true; window.sessionStorage = makeStore({ full: true }); registry.keep.checked = false; "
                "registry.keep.fire('change')")
    assert run(page, "[readHistory().length, keepsHistory(), registry.keep.checked, registry['keep-failed'].hidden, registry['unkeep-failed'].hidden]") == [
        1, True, True, True, False]  # the message says the list could not be taken off the device, not the opposite
    assert run(page, "'history' in window.localStorage.data") is True


def test_two_tabs_do_not_redraw_each_other_forever_because_the_page_only_follows_its_own_keys(page):
    history_page(page)
    start(page, "globalThis.draws = 0; const original = drawHistory; drawHistory = (...args) => { draws++; return original(...args); }")
    for key, redraws in (("probe", 0), ("lang", 0), ("prefill", 0), ("history", 1), ("keep_history", 1), (None, 1)):  # None: clear() in another tab
        start(page, "draws = 0")
        start(page, f"window.fire('storage', {{ key: {json.dumps(key)} }})")
        assert run(page, "draws") == redraws, key
    # the page's own storage test writes the key "probe"; the other tab hears it and must not answer
    start(page, "setKeepHistory(true); draws = 0; storageState()")
    assert run(page, "draws") == 0


def test_unticking_keep_leaves_no_secret_copy_when_the_browser_refuses_part_of_it(page):
    history_page(page, ("A ?", REPLY))
    # ticking: the list reaches the device but the flag is refused: the copy on the device is taken away again
    start(page, "window.localStorage = makeStore({ failSet: ['keep_history'] }); registry.keep.checked = true; registry.keep.fire('change')")
    assert run(page, "['history' in window.localStorage.data, 'history' in window.sessionStorage.data, keepsHistory(), registry.keep.checked]") == [
        False, True, False, False]
    assert run(page, "[registry['keep-failed'].hidden, registry['unkeep-failed'].hidden]") == [False, True]
    # unticking: the flag goes but the copy on the device cannot be removed: the message says so
    start(page, "window.localStorage = makeStore({ failRemove: ['history'] }); window.sessionStorage = makeStore(); setKeepHistory(true) ;"
                "window.localStorage.data.keep_history = '1'; registry.keep.checked = false; registry.keep.fire('change')")
    assert run(page, "[keepsHistory(), 'history' in window.localStorage.data, registry['unkeep-failed'].hidden]") == [False, True, False]
    # unticking: the flag itself is refused: nothing changes and the box stays ticked
    start(page, "window.localStorage = makeStore({ failRemove: ['keep_history'] }); window.sessionStorage = makeStore(); window.localStorage.data.keep_history = '1';"
                "registry.keep.checked = false; registry.keep.fire('change')")
    assert run(page, "[keepsHistory(), registry.keep.checked, registry['unkeep-failed'].hidden, 'history' in window.sessionStorage.data]") == [True, True, False, False]


def test_a_failed_read_is_never_taken_for_an_empty_list_so_a_write_cannot_wipe_the_kept_list(page):
    give(page, "reply", REPLY)
    start(page, 'addToHistory("A", reply); addToHistory("B", { ...reply, request_id: "b" })')
    start(page, "globalThis.kept = window.sessionStorage.data.history; window.sessionStorage = makeStore({ failGet: ['history'] }); "
                "window.sessionStorage.data.history = kept")
    assert run(page, 'addToHistory("C", { ...reply, request_id: "c" })') is False
    start(page, "deleteEntry('b'); updateEntry('b', { english: 'x' })")
    assert run(page, "window.sessionStorage.data.history === kept") is True  # nothing was written over it
    assert run(page, "setKeepHistory(true)") == "failed" and run(page, "window.sessionStorage.data.history === kept") is True


def test_erase_says_so_when_the_browser_refuses_and_the_question_closes_when_the_list_is_empty(page):
    history_page(page, ("A ?", REPLY))
    start(page, "const store = makeStore({ failRemove: ['history'] }); store.data.history = window.sessionStorage.data.history; window.sessionStorage = store; drawHistory()")
    start(page, "registry.clear.click(); registry['confirm-yes'].click()")
    assert run(page, "[registry['erase-failed'].hidden, readHistory().length]") == [False, 1]
    start(page, "window.sessionStorage = makeStore(); registry.clear.click(); registry['confirm-yes'].click()")
    assert run(page, "registry['erase-failed'].hidden") is True
    history_page(page, ("A ?", REPLY))  # the question is open, then the last entry is deleted
    start(page, "registry.clear.click(); lastDeleteAt = 0; byTag(byClass(registry.history, 'hist')[0], 'button')[2].click()")
    assert run(page, "registry.confirm.hidden") is True


def test_a_full_storage_still_shows_the_list_with_a_message_and_a_blocked_one_says_it_cannot_keep(page):
    history_page(page, ("A ?", REPLY), ("B ?", {**REPLY, "request_id": "b"}))
    start(page, "const full = makeStore({ full: true }); full.data.history = window.sessionStorage.data.history; window.sessionStorage = full; drawHistory()")
    assert run(page, "byClass(registry.history, 'hist').length") == 2  # the list can be read, so it is shown
    assert "stockage plein ou bloqué" in run(page, "registry.history.children[0].textContent")
    assert run(page, "toggles().length") == 2
    start(page, "toggles()[0].click()")  # and it can still be opened
    assert run(page, "byClass(registry.history, 'answer').length") == 1
    start(page, "window.sessionStorage = makeStore({ broken: true }); drawHistory()")  # nothing can even be read
    assert run(page, "byClass(registry.history, 'hist').length") == 0
    assert "ne permet pas de garder l'historique" in run(page, "registry.history.textContent")


def body_text(page, index):
    """The text inside the opened entry at this place of the list."""
    return run(page, f"byClass(registry.history, 'hist-body')[{index}].textContent")


def test_a_damaged_entry_says_it_is_unreadable_instead_of_doing_nothing_and_the_others_still_open(page):
    history_page(page, ("Bonne ?", REPLY))
    start(page, """const list = readHistory();
      const base = list[0].reply;
      const bad = (id, changes, at) => ({ id, at: at || list[0].at, question: "Abîmée " + id, reply: { ...base, request_id: id, ...changes } });
      window.sessionStorage.data.history = JSON.stringify([
        bad("c1", { claims: "text" }), bad("c2", { claims: [{ text: "x", citations: [{ label: "L1" }] }] }),
        bad("c3", { masked: "email" }), bad("c4", { masked: ["passport"], question_masked: "q" }), bad("c5", {}, "not a date"), list[0]]);
      drawHistory();""")
    assert run(page, "byClass(registry.history, 'hist').length") == 6
    for index in range(6):
        start(page, f"toggles()[{index}].click()")
    assert body_text(page, 0) == body_text(page, 1) == "Cette entrée est illisible. Vous pouvez la supprimer."  # a text for the claims, a citation without units
    assert "Quatre mois pour un cadre." in body_text(page, 2) and "masqué" not in body_text(page, 2)  # masked as a text: no notice, the answer is shown
    assert "des données personnelles" in body_text(page, 3) and "Quatre mois pour un cadre." in body_text(page, 3)  # a kind of data this page does not know
    assert "Quatre mois pour un cadre." in body_text(page, 4) and "Réponse du" not in body_text(page, 4)  # a date that cannot be read: no date line
    assert "Réponse du" in body_text(page, 5)


def test_an_entry_without_an_id_or_a_question_or_with_a_repeated_id_is_not_listed_twice(page):
    history_page(page)
    start(page, """window.sessionStorage.data.history = JSON.stringify([
      { id: "a", at: "2026-11-24T10:00:00Z", question: "Un", reply: { outcome: "answered", claims: [] } },
      { id: "a", at: "2026-11-24T09:00:00Z", question: "Deux", reply: { outcome: "answered", claims: [] } },
      { question: "Sans id", reply: { outcome: "answered" } }, { id: "b", question: 5, reply: {} }, { id: "c", question: "Sans réponse" }, null, 3])""")
    assert run(page, "readHistory().map((e) => e.question)") == ["Un"]


def test_a_second_delete_within_half_a_second_is_ignored_so_a_double_click_removes_one_entry(page):
    history_page(page, ("A ?", REPLY), ("B ?", {**REPLY, "request_id": "b"}), ("C ?", {**REPLY, "request_id": "c"}))
    start(page, "lastDeleteAt = 0; globalThis.clock = 1000000; Date.now = () => clock")
    start(page, "byTag(byClass(registry.history, 'hist')[0], 'button')[2].click()")  # deletes C
    start(page, "clock += 100; byTag(byClass(registry.history, 'hist')[0], 'button')[2].click()")  # the same place, now B: a double click
    assert run(page, "readHistory().map((e) => e.question)") == ["B ?", "A ?"]
    start(page, "clock += 600; byTag(byClass(registry.history, 'hist')[0], 'button')[2].click()")  # a deliberate second delete
    assert run(page, "readHistory().map((e) => e.question)") == ["A ?"]


def test_a_missing_text_shows_its_key_and_does_not_break_the_page(page):
    assert run(page, "t('not_a_key')") == "not_a_key"
    give(page, "reply", {**REPLY, "masked": ["passport"], "question_masked": "Q"})
    assert "des données personnelles" in run(page, "maskedNotice(reply).textContent")


def test_wording_details_the_masked_question_label_the_edit_button_and_the_path_heading(page):
    give(page, "reply", {**REPLY, "masked": ["email"], "question_masked": "Can I? [e-mail]", "question_fr": "Puis-je ? [e-mail]"})
    assert "Votre question avec la partie masquée : « Can I? [e-mail] »" in run(page, "maskedNotice(reply).textContent")
    start(page, 'lang = "en"')
    assert "Your question with the masked part: “Can I? [e-mail]”" in run(page, "maskedNotice(reply).textContent")
    assert run(page, "byClass(translatedLine(reply), 'linklike')[0].textContent") == "Edit the French"
    assert run(page, "t('where')") == "Where in the law? (in French)"
    start(page, 'lang = "fr"')
    assert run(page, "byClass(translatedLine(reply), 'linklike')[0].textContent") == "Modifier"


def test_a_long_word_cannot_push_the_history_sideways():
    css = (STATIC / "style.css").read_text()
    rule = next(line for line in css.splitlines() if ".hist .hist-q" in line and "overflow-wrap" in line)
    assert ".hist .hist-fr" in rule and "blockquote" in rule


def slow_fetch(page, status, body):
    """A fetch that answers only when `release()` is called: the request stays in flight."""
    give(page, "slowReply", {"status": status, "body": body})
    page.eval("""globalThis.requests = [];
      fetch = (url, options) => { requests.push([url, JSON.parse(options.body)]);
        return new Promise((resolve) => { globalThis.release = () => resolve({ status: slowReply.status, headers: { get: () => null }, json: async () => slowReply.body }); }); };""")


def first_page(page):
    for name in ("go", "result", "question", "count", "english", "translate", "cards"):
        page.eval(f'registry.{name} = new FakeNode("{"button" if name in ("go", "translate") else "div"}")')
    page.eval("registry.question.value = ''; registry.english.hidden = true")


def test_only_one_question_runs_at_a_time_on_the_first_page_and_what_is_drawn_meanwhile_is_the_busy_line(page):
    first_page(page)
    slow_fetch(page, 200, REPLY)
    start(page, 'examples = [{ question: "Carte ?", label: { fr: "C", en: "C" }, source: "ct" }]; drawExamples()')
    start(page, 'ask("Q1 ?"); ask("Q2 ?"); ask("Q3 ?", true); ask("Q4 ?", false, true)')
    assert run(page, "requests") == [["/ask", {"question": "Q1 ?", "translate": False}]]  # the others were not even sent
    assert run(page, "[registry.go.disabled, registry.translate.disabled]") == [True, True]
    start(page, "byClass(registry.cards, 'card')[0].click()")
    assert run(page, "registry.question.value") == ""  # a card does not change the box while an answer is awaited
    start(page, 'lang = "en"; show()')  # a language switch while the request runs
    assert run(page, "registry.result.textContent") == "Searching…"
    start(page, "release()")
    assert run(page, "[registry.go.disabled, registry.translate.disabled, byClass(registry.result, 'answer').length]") == [False, False, 1]
    assert run(page, "document.activeElement === registry.result") is True  # the keyboard focus lands on the new answer
    start(page, 'ask("Q5 ?")')
    assert run(page, "requests.length") == 2  # free again


def test_a_vote_that_cannot_be_sent_says_so_and_a_double_click_sends_one_vote(page):
    page.eval('fetch = async () => { throw new Error("offline"); }')
    start(page, "globalThis.box = voteBox('r'.repeat(32)); byTag(box, 'button')[0].click()")
    assert run(page, "byClass(box, 'count').map((n) => n.textContent)") == ["Le vote n'a pas pu être enregistré."]
    slow_fetch(page, 200, {})
    start(page, "byTag(box, 'button')[0].click(); byTag(box, 'button')[0].click(); byTag(box, 'button')[1].click()")
    assert run(page, "requests.length") == 1  # the others wait for the first one
    start(page, "release()")
    assert "Merci" in run(page, "box.textContent")


@pytest.mark.parametrize("body", [{}, [], {"detail": "x"}, {"outcome": "unheard_of"}, {"outcome": "answered"}, {"outcome": "answered", "claims": []},
                                  {"outcome": "answered", "claims": "text"}, {"outcome": "rate_limited"}, "text", 5])
def test_a_reply_with_status_200_that_is_not_a_reply_this_page_knows_is_a_failure_message_and_not_a_refusal_or_a_blank(page, body):
    result_area(page)
    fake_fetch(page, 200, body)
    start(page, 'ask("Q ?")')
    assert run(page, "registry.result.textContent") == "Le service a rencontré un problème. Réessayez dans un instant."
    assert run(page, "readHistory()") == []


def test_a_reply_whose_claims_have_the_wrong_shape_is_a_failure_message_and_not_an_error(page):
    result_area(page)
    fake_fetch(page, 200, {**REPLY, "claims": [{"text": "x"}, 5, {"text": "y", "citations": "z"}]})
    start(page, 'ask("Q ?")')
    assert "problème" in run(page, "registry.result.textContent") and run(page, "registry.go.disabled") is False


def test_an_invalid_citation_is_a_refusal_in_words(page):
    result_area(page)
    fake_fetch(page, 200, {**REPLY, "outcome": "invalid_citation", "claims": []})
    start(page, 'ask("Q ?")')
    assert "Pas de réponse" in run(page, "registry.result.textContent")
    assert run(page, "readHistory()") == []  # not a kind of reply the history keeps


@pytest.mark.parametrize("english", ["", "   ", None, 5])
def test_an_empty_translation_is_a_failure_and_not_an_empty_block(page, english):
    give(page, "reply", {**REPLY, "question_fr": "Quelle durée ?"})
    fake_fetch(page, 200, {"english": english})
    start(page, "globalThis.box = englishBlock(reply); byTag(box, 'button')[0].click()")
    assert "n'a pas pu être faite" in run(page, "box.textContent") and run(page, "byTag(box, 'button')[0].disabled") is False
    assert run(page, "reply.english === undefined")


def test_a_translation_that_arrives_after_the_first_page_was_drawn_again_is_shown_and_asked_for_once(page):
    first_page(page)
    fake_fetch(page, 200, {**REPLY, "question_fr": "Quelle durée ?"})
    start(page, 'ask("How long?", true)')
    slow_fetch(page, 200, {"english": "Four months. [1]"})
    start(page, "byTag(registry.result, 'button').filter((b) => b.className === 'pill')[0].click()")
    start(page, 'lang = "en"; show()')  # the visitor switches language while it runs: new nodes
    again = "byTag(registry.result, 'button').filter((b) => b.className === 'pill')[0]"
    assert run(page, f"{again}.disabled") is True  # the new button is already off
    start(page, f"{again}.click()")
    assert run(page, "requests.length") == 1
    start(page, "release()")
    assert "Four months." in run(page, "registry.result.textContent")
    assert run(page, "byClass(registry.result, 'en-answer')[0].children.filter((c) => c.tag === 'button').length") == 0
    assert run(page, "requests.length") == 1


def test_the_keyboard_focus_goes_to_the_translation_when_it_arrives(page):
    give(page, "reply", {**REPLY, "question_fr": "Quelle durée ?"})
    fake_fetch(page, 200, {"english": "Four months. [1]"})
    page.eval('registry.box = null')
    start(page, "globalThis.box = englishBlock(reply); registry.shown = box; byTag(box, 'button')[0].click()")
    assert run(page, "document.activeElement === box") is True


@pytest.mark.parametrize("status, body", [(500, {"detail": "x"}), (429, {"detail": "x"}), (404, {"detail": "no such answer"}), (200, {"english": " "})])
def test_a_translation_that_fails_after_the_page_was_drawn_again_leaves_a_usable_button_and_a_message_on_the_box_on_screen(page, status, body):
    first_page(page)
    fake_fetch(page, 200, {**REPLY, "question_fr": "Quelle durée ?"})
    start(page, 'ask("How long?", true)')
    slow_fetch(page, status, body)
    pill = "byTag(registry.result, 'button').filter((b) => b.className === 'pill')[0]"
    start(page, f"{pill}.click()")
    start(page, 'lang = "en"; show()')  # new nodes while the request runs
    assert run(page, f"{pill}.disabled") is True
    start(page, "release()")
    assert run(page, f"{pill}.disabled") is False  # usable again
    assert run(page, "byClass(registry.result, 'en-answer')[0].textContent").strip() != "English translation of this answer"  # and a message is shown
    assert run(page, "byClass(registry.result, 'en-answer')[0].children.filter((c) => c.className === 'count').length") == 1


def test_a_model_failure_after_a_good_translation_keeps_the_articles_and_is_not_called_a_translation_failure(page):
    result_area(page)
    fake_fetch(page, 502, {**REPLY, "outcome": "llm_error", "claims": [], "question_fr": "Quelle durée ?"})
    start(page, 'ask("How long?", true)')
    text = run(page, "registry.result.textContent")
    assert "Le modèle n'a pas répondu" in text and "traduction de votre question" not in text and "L1221-19" in text


@pytest.mark.parametrize("status, body", [(0, None), (422, {"detail": []}), (500, None), (200, {}), (429, {"detail": "x"}), (502, {**REPLY, "outcome": "llm_error", "claims": []})])
def test_the_french_line_stays_after_a_failed_ask_again_from_it_whatever_the_failure(page, status, body):
    result_area(page)
    fake_fetch(page, 200, {**REPLY, "question_fr": "Quelle durée ?"})
    start(page, 'ask("How long?", true)')
    if status == 0:
        page.eval('fetch = async () => { throw new Error("offline"); }')
    else:
        fake_fetch(page, status, body)
    start(page, 'ask("Quelle durée pour un cadre ?", false, true)')
    assert run(page, "byClass(registry.result, 'tr-line').length") == 1, (status, body)
    assert run(page, "byTag(byClass(registry.result, 'tr-line')[0], 'q')[0].textContent") == "Quelle durée pour un cadre ?"


def test_a_second_thumb_while_the_first_vote_is_on_its_way_changes_nothing_on_the_screen(page):
    slow_fetch(page, 200, {})
    start(page, "globalThis.box = voteBox('r'.repeat(32)); const thumbs = byClass(box, 'thumb'); thumbs[0].click(); thumbs[1].click()")
    assert run(page, "byClass(box, 'thumb').map((b) => b.getAttribute('aria-pressed'))") == ["true", "false"]
    assert run(page, "requests.length") == 1


def test_an_empty_submit_while_a_question_runs_leaves_the_busy_line(page):
    first_page(page)
    page.eval("registry.ask = new FakeNode('form'); registry.ask.requestSubmit = () => {}; registry.question.value = ''; "
              "fetch = async () => ({ json: async () => [] })")
    start(page, "setup()")  # the form listens
    slow_fetch(page, 200, REPLY)
    start(page, 'ask("Q ?")')
    assert run(page, "registry.result.textContent") == "Recherche en cours…"
    start(page, "registry.ask.fire('submit')")  # the form: an empty box, while the request runs
    assert run(page, "registry.result.textContent") == "Recherche en cours…"


def test_a_double_failure_of_ticking_keep_says_the_copy_stays_on_the_device(page):
    history_page(page, ("A ?", REPLY))
    start(page, "window.localStorage = makeStore({ failSet: ['keep_history'], failRemove: ['history'] }); registry.keep.checked = true; registry.keep.fire('change')")
    assert run(page, "['history' in window.localStorage.data, registry['unkeep-failed'].hidden, registry['keep-failed'].hidden]") == [True, False, True]


def test_an_answer_whose_claims_have_no_citations_is_neither_drawn_nor_kept(page):
    result_area(page)
    for claims in ([{"text": "x"}], [{"text": "x", "citations": "z"}], [{"text": "x", "citations": [{"label": "L1"}]}], ["x"], [None]):
        fake_fetch(page, 200, {**REPLY, "claims": claims})
        start(page, 'ask("Q ?")')
        assert "problème" in run(page, "registry.result.textContent"), claims
        assert run(page, "readHistory()") == [], claims


def test_a_failure_while_showing_the_result_area_does_not_leave_the_page_waiting_for_ever(page):
    first_page(page)
    page.eval("registry.result.scrollIntoView = () => { throw new Error('no scrolling here'); }")
    fake_fetch(page, 200, REPLY)
    start(page, 'ask("Q1 ?")')
    assert run(page, "[asking, registry.go.disabled]") == [None, False]  # released, and the buttons are back
    page.eval("registry.result.scrollIntoView = () => {}")
    start(page, 'ask("Q2 ?")')
    assert run(page, "requests.length") == 1 and run(page, "byClass(registry.result, 'answer').length") == 1  # the next question works


def test_the_focus_does_not_leave_a_box_the_visitor_is_typing_in_when_a_translation_arrives(page):
    give(page, "reply", {**REPLY, "question_fr": "Quelle durée ?"})
    fake_fetch(page, 200, {"english": "Four months. [1]"})
    start(page, "globalThis.box = englishBlock(reply); registry.question = new FakeNode('textarea'); registry.question.focus(); byTag(box, 'button')[0].click()")
    assert run(page, "document.activeElement === registry.question") is True


def test_the_first_page_takes_the_text_to_edit_once_and_fits_it_to_the_box(page):
    page.eval("""for (const name of ["ask", "question", "translate", "count", "english", "result"]) registry[name] = new FakeNode("div");
      registry.ask.requestSubmit = () => {}; fetch = async () => ({ json: async () => [] });""")
    start(page, 'window.sessionStorage.setItem("prefill", "x".repeat(600)); setup()')
    assert run(page, "registry.question.value.length") == 500 and run(page, "registry.count.textContent") == "500 / 500"
    assert run(page, "Object.keys(window.sessionStorage.data)") == []  # taken once: a reload shows an empty box
    assert "Question reprise de votre historique" in run(page, "registry.result.textContent")
    start(page, "registry.question.value = ''; setup()")
    assert run(page, "registry.question.value") == ""
    start(page, "window.sessionStorage = makeStore({ broken: true }); setup()")  # refused storage: an empty box, no error
    assert run(page, "registry.question.value") == ""


def test_the_history_page_says_so_when_it_is_empty_and_follows_the_language(page):
    page.eval('registry.history = new FakeNode("section")')
    start(page, "drawHistory()")
    assert run(page, "registry.history.textContent") == "Aucune question pour le moment. La liste de cet onglet disparaît quand vous le fermez : cochez la case ci-dessus pour la garder sur cet appareil."
    start(page, 'lang = "en"; drawHistory()')
    assert run(page, "registry.history.textContent") == "No questions yet. This tab's list is lost when you close the tab: tick the box above to keep it on this device."
    start(page, 'window.localStorage.setItem("keep_history", "1"); drawHistory()')  # a kept history has no such hint
    assert run(page, "registry.history.textContent") == "No questions yet."


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


def test_an_answer_drawn_from_the_history_has_no_vote_or_list_of_articles_and_offers_the_translation_only_while_none_is_kept(page):
    give(page, "reply", {**REPLY, "question_fr": "Quelle durée ?"})
    assert run(page, "byClass(replyNode(reply, 200, null, true), 'vote').length + byClass(replyNode(reply, 200, null, true), 'found').length") == 0
    assert run(page, "byTag(byClass(replyNode(reply, 200, null, true), 'en-answer')[0], 'button').length") == 1  # asked in English: the button
    give(page, "kept", {**REPLY, "question_fr": "Quelle durée ?", "english": "Four months. [1]"})
    node = "byClass(replyNode(kept, 200, null, true), 'en-answer')[0]"
    assert run(page, f"byTag({node}, 'button').length") == 0 and "Four months." in run(page, f"{node}.textContent")  # kept: the text, no button
    give(page, "french", REPLY)  # a French visitor, French page: nothing to translate
    assert run(page, "byClass(replyNode(french, 200, null, true), 'en-answer').length") == 0


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


@pytest.mark.parametrize("status", [429, 502, 503, 500, 504, 404, 413, 411])
@pytest.mark.parametrize("body", [{"detail": "the service is busy, try again in a moment"}, None, "Internal Server Error", [], {}])
def test_whatever_body_an_error_has_the_result_is_a_message_and_never_a_blank_or_a_refusal_of_the_model(page, status, body):
    give(page, "body", body)
    for language in ("fr", "en"):
        start(page, f'lang = "{language}"')
        text = run(page, f"replyNode(body, {status}, 5).textContent")
        assert text, (status, body, language)
        assert "texts of this service" not in text and "textes de ce service" not in text  # not "No answer: the law is silent"
        if status in (500, 504, 404, 413, 411):
            assert text == {"fr": "Le service a rencontré un problème. Réessayez dans un instant.", "en": "The service had a problem. Try again in a moment."}[language]


def test_a_request_whose_answer_is_not_a_reply_shows_a_message_and_keeps_nothing(page):
    result_area(page)
    for status, body in ((500, None), (504, "text"), (200, None), (200, "text"), (200, 5), (500, {"detail": "x"})):
        fake_fetch(page, status, body)
        start(page, 'ask("Q ?", false, true)')  # also from the French field: a text reply cannot take a property
        assert "problème" in run(page, "registry.result.textContent"), (status, body)
        assert run(page, "readHistory()") == []
        assert run(page, "registry.go.disabled") is False


@pytest.mark.parametrize("text, english", [
    ("Probation period?", True), ("Notice period?", True), ("Dismissal", True), ("overtime pay", True), ("Maternity leave", True),
    ("Quelle durée ?", False), ("Licenciement", True), ("congé", False), ("Préavis", False), ("", False), ("   ", False), ("?", False),
    ("Est-ce légal ?", False), ("le préavis", False), ("RGPD article 17", True), ("L1221-13", True)])
def test_a_short_question_is_offered_the_translation_on_the_english_page_unless_it_looks_french(page, text, english):
    start(page, 'lang = "en"')
    assert run(page, f"offersTranslation({json.dumps(text)})") is english


def test_on_the_french_page_only_clearly_english_questions_are_offered_the_translation_and_a_language_switch_recomputes_it(page):
    assert run(page, 'offersTranslation("Probation period?")') is False  # French page: the old rule
    assert run(page, 'offersTranslation("What is the notice period?")') is True
    page.eval("""for (const name of ["ask", "question", "translate", "count", "english", "result"]) registry[name] = new FakeNode("div");
      registry.ask.requestSubmit = () => {}; fetch = async () => ({ json: async () => [] });
      registry.question.value = "Probation period?"; registry.english.hidden = true;
      globalThis.switcher = new FakeNode("button"); switcher.dataset.lang = "en";
      document.querySelectorAll = (selector) => (selector === "[data-lang]" ? [switcher] : []);""")
    start(page, "setup()")
    start(page, "switcher.click()")  # the visitor picks EN
    assert run(page, "[lang, registry.english.hidden]") == ["en", False]


def test_the_page_follows_the_language_for_the_messages_it_builds(page):
    give(page, "reply", REPLY)
    start(page, 'lang = "en"')
    assert "Answer (in French)" in run(page, "replyNode(reply, 200, null).textContent") and "Cited passages" in run(page, "replyNode(reply, 200, null).textContent")
    assert "Too many requests from you. Try again in 9 seconds." in run(page, "replyNode(reply, 429, 9).textContent")


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


@pytest.mark.parametrize("status, retry, expected", [(429, "7", "Réessayez dans 7 s"), (502, None, "n'a pas pu être faite"),
                                                      (503, None, "n'a pas pu être faite")])
def test_a_translation_that_fails_says_so_and_lets_the_visitor_try_again(page, status, retry, expected):
    give(page, "reply", {**REPLY, "question_fr": "Quelle durée ?"})
    fake_fetch(page, status, {"detail": "x"}, retry)
    start(page, "globalThis.box = englishBlock(reply); byTag(box, 'button')[0].click()")
    assert expected in run(page, "box.textContent")
    assert run(page, "byTag(box, 'button')[0].disabled") is False  # the button is back


def test_an_answer_the_service_no_longer_holds_cannot_be_translated_and_the_button_does_not_come_back(page):
    give(page, "reply", {**REPLY, "question_fr": "Quelle durée ?"})
    fake_fetch(page, 410, {"detail": "this answer is no longer stored"})
    start(page, "globalThis.box = englishBlock(reply); byTag(box, 'button')[0].click()")
    assert "ne garde plus cette réponse (7 jours)" in run(page, "box.textContent")
    assert run(page, "byTag(box, 'button')[0].disabled") is True and run(page, "requests.length") == 1
    assert run(page, "englishBlock(reply).textContent") == "Le service ne garde plus cette réponse (7 jours) : la traduction n'est plus possible."  # remembered
    assert run(page, "byTag(englishBlock(reply), 'button').length") == 0  # no button after a redraw
    give(page, "fresh", {**REPLY, "question_fr": "Quelle durée ?"})
    start(page, 'lang = "en"; globalThis.box2 = englishBlock(fresh); byTag(box2, "button")[0].click()')
    assert "no longer holds this answer (7 days)" in run(page, "box2.textContent")


def test_a_404_on_a_translation_says_the_service_never_had_the_answer_and_is_not_remembered_as_gone(page):
    give(page, "reply", {**REPLY, "question_fr": "Quelle durée ?"})
    fake_fetch(page, 404, {"detail": "no such answer"})
    start(page, "globalThis.box = englishBlock(reply); byTag(box, 'button')[0].click()")
    assert "n'a pas gardé cette réponse" in run(page, "box.textContent") and "7 jours" not in run(page, "box.textContent")
    assert run(page, "reply.english_gone === undefined") is True and run(page, "byTag(box, 'button')[0].disabled") is False


def test_an_entry_older_than_seven_days_says_at_once_that_its_answer_cannot_be_translated(page):
    history_page(page, ("How long?", {**REPLY, "question_fr": "Quelle durée ?"}))
    fake_fetch(page, 200, {"english": "x"})
    start(page, "toggles()[0].click()")
    assert run(page, "byTag(byClass(registry.history, 'en-answer')[0], 'button').length") == 1  # today: the button
    start(page, """const list = JSON.parse(window.sessionStorage.data.history);
      list[0].at = new Date(Date.now() - 8 * 24 * 3600 * 1000).toISOString(); window.sessionStorage.data.history = JSON.stringify(list);
      openEntries.clear(); drawHistory(); toggles()[0].click()""")
    assert run(page, "byTag(byClass(registry.history, 'en-answer')[0], 'button').length") == 0
    assert "ne garde plus cette réponse" in run(page, "byClass(registry.history, 'en-answer')[0].textContent")
    assert run(page, "requests.length") == 0  # nothing was asked of the service


def test_a_failed_translation_of_the_question_is_told_as_such_and_has_no_vote_or_articles(page):
    result_area(page)
    fake_fetch(page, 502, {**REPLY, "outcome": "llm_error", "claims": [], "articles": [], "reason": "La traduction de la question a échoué."})
    start(page, 'ask("How long?", true)')
    assert run(page, "registry.result.textContent") == "La traduction de votre question a échoué. Réessayez, ou écrivez-la en français."
    start(page, 'lang = "en"; show()')
    assert run(page, "registry.result.textContent") == "The translation of your question failed. Try again, or write it in French."
    fake_fetch(page, 502, {**REPLY, "outcome": "llm_error", "claims": [], "articles": []})  # the model failed on a French question: no articles to show
    start(page, 'ask("Quelle durée ?")')
    assert run(page, "registry.result.textContent").startswith("The AI model did not answer. Try again in a moment.")
    assert "shown below" not in run(page, "registry.result.textContent")
    fake_fetch(page, 502, {**REPLY, "outcome": "llm_error", "claims": []})  # with articles: they are shown
    start(page, 'ask("Quelle durée 2 ?")')
    assert "The articles found are shown below." in run(page, "registry.result.textContent")


def test_the_english_notice_names_the_masked_labels_in_english_and_an_unknown_kind_is_personal_data(page):
    labels = ["[e-mail]", "[date de naissance]", "[IBAN]", "[numéro de sécurité sociale]", "[carte bancaire]", "[téléphone]"]
    give(page, "reply", {**REPLY, "masked": ["birth", "nir", "card", "phone", "email", "iban"], "question_masked": " ".join(labels)})
    start(page, 'lang = "en"')
    text = run(page, "maskedNotice(reply).textContent")
    assert "[e-mail] [date of birth] [IBAN] [social security number] [bank card] [telephone]" in text
    assert "é" not in text.split("avoid")[0].split("question with the masked part")[1]  # no French label is left in the quoted question
    start(page, 'lang = "fr"')
    assert "[numéro de sécurité sociale]" in run(page, "maskedNotice(reply).textContent")  # the French page keeps them
    give(page, "odd", {**REPLY, "masked": ["passport", "email"], "question_masked": "Q"})
    start(page, 'lang = "en"')
    assert "personal data, an e-mail address" in run(page, "maskedNotice(odd).textContent")


def test_the_list_says_to_make_room_only_when_there_is_something_to_delete(page):
    history_page(page, ("A ?", REPLY))
    start(page, "const full = makeStore({ full: true }); full.data.history = window.sessionStorage.data.history; window.sessionStorage = full; drawHistory()")
    assert "Supprimez des entrées" in run(page, "registry.history.children[0].textContent")
    start(page, "full.data.history = '[]'; drawHistory()")
    assert "Supprimez" not in run(page, "registry.history.children[0].textContent")


def test_the_english_messages_say_seconds_and_the_ai_model(page):
    start(page, 'lang = "en"')
    assert run(page, "t('limited', { n: waitText(7) })") == "Too many requests from you. Try again in 7 seconds."
    assert run(page, "t('limited', { n: waitText(1) })") == "Too many requests from you. Try again in 1 second."
    start(page, 'lang = "fr"')
    assert run(page, "t('limited', { n: waitText(1) })") == "Trop de demandes de votre part. Réessayez dans 1 s."
    start(page, 'lang = "en"')
    assert run(page, "t('network')") == "The service is not responding. Try again in a moment."
    assert run(page, "t('upstream')").startswith("The AI model did not answer.")


def test_the_notes_of_failed_tries_do_not_pile_up_and_a_later_success_replaces_them(page):
    give(page, "reply", {**REPLY, "question_fr": "Quelle durée ?"})
    fake_fetch(page, 500, {"detail": "x"})
    start(page, "globalThis.box = englishBlock(reply)")
    for _ in range(3):  # three tries that fail, one after the other
        start(page, "byTag(box, 'button')[0].click()")
        assert run(page, "box.textContent.split('n\\'a pas pu être faite').length - 1") == 1
    fake_fetch(page, 200, {"english": "Four months. [1]"})
    start(page, "byTag(box, 'button')[0].click()")
    assert "pas pu" not in run(page, "box.textContent") and "Four months." in run(page, "box.textContent")


def test_a_translation_that_arrives_while_the_list_was_drawn_again_still_shows_in_the_entry(page):
    history_page(page, ("How long?", {**REPLY, "question_fr": "Quelle durée ?"}))
    page.eval("""fetch = () => new Promise((resolve) => { globalThis.release = () => resolve({ status: 200, headers: { get: () => null },
      json: async () => ({ english: "Four months. [1]" }) }); });""")
    start(page, "toggles()[0].click(); byClass(registry.history, 'en-answer')[0].children.filter((c) => c.tag === 'button')[0].click()")
    start(page, 'lang = "en"; drawHistory()')  # a language change while the request runs: new nodes, the old box is gone
    assert run(page, "byClass(registry.history, 'en-answer')[0].textContent").startswith("English translation of this answer")  # the button again
    start(page, "release()")
    assert run(page, "readHistory()[0].reply.english") == "Four months. [1]"
    assert "Four months." in run(page, "byClass(registry.history, 'en-answer')[0].textContent")
    assert run(page, "byClass(registry.history, 'en-answer')[0].children.filter((c) => c.tag === 'button').length") == 0


def test_an_answer_found_gone_is_remembered_in_its_entry(page):
    history_page(page, ("How long?", {**REPLY, "question_fr": "Quelle durée ?"}))
    fake_fetch(page, 410, {"detail": "this answer is no longer stored"})
    start(page, "toggles()[0].click(); byClass(registry.history, 'en-answer')[0].children.filter((c) => c.tag === 'button')[0].click()")
    assert run(page, "readHistory()[0].reply.english_gone") is True
    start(page, "drawHistory()")
    assert "Le service ne garde plus cette réponse" in run(page, "byClass(registry.history, 'en-answer')[0].textContent")
    assert run(page, "byClass(registry.history, 'en-answer')[0].children.filter((c) => c.tag === 'button').length") == 0
    assert run(page, "requests.length") == 1


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
