// The history of the visitor (step 0f, part 4): storage, the entries and the history page. Loaded before app.js, which
// calls it; it uses the helpers of app.js (t, make, lang, ...) only when called.
"use strict";

// ---- The history of the visitor: in the browser only, never sent to the service. By default it lives in the memory of the
// tab (sessionStorage) and disappears when the tab is closed; if the visitor asks, it is kept on the device (localStorage)
// until the visitor erases it. Storage can be refused or full: the history is a convenience and never breaks the page.
const HISTORY_KEY = "history";
const KEEP_KEY = "keep_history";
const HISTORY_MAX = 30;
const HISTORY_OUTCOMES = ["answered", "refused_by_model", "refused_weak_retrieval"];

function browserStore(persistent) {
  try { return persistent ? window.localStorage : window.sessionStorage; } catch (e) { return null; }
}

// "blocked": the list cannot even be read; "full": it can be read but nothing can be written (storage full, or a strict private
// mode); "ok". The page says so instead of looking broken, and a list that can be read is always shown.
function storageState() {
  const store = browserStore(keepsHistory());
  try { store.getItem(HISTORY_KEY); } catch (e) { return "blocked"; }
  try { store.setItem("probe", "1"); store.removeItem("probe"); return "ok"; } catch (e) { return "full"; }
}

function keepsHistory() {
  try { return browserStore(true).getItem(KEEP_KEY) === "1"; } catch (e) { return false; }
}

// The kept list, or null when the browser cannot be read at all: a writer must not take that for an empty list and write over it.
function loadHistory() {
  let raw;
  try { raw = browserStore(keepsHistory()).getItem(HISTORY_KEY); } catch (e) { return null; }
  try {
    const list = JSON.parse(raw || "[]");
    if (!Array.isArray(list)) return [];
    const seen = new Set(); // two entries with one id (a list edited by hand) would open and be deleted together
    return list.filter((entry) => {
      const fit = entry && typeof entry.id === "string" && typeof entry.question === "string" && entry.reply && typeof entry.reply === "object"
        && !seen.has(entry.id);
      if (fit) seen.add(entry.id);
      return fit;
    });
  } catch (e) { return []; } // damaged text: nothing to keep
}

function readHistory() {
  return loadHistory() ?? [];
}

// False when the browser refused or had no room: the caller may say so.
function writeHistoryTo(persistent, list) {
  try { browserStore(persistent).setItem(HISTORY_KEY, JSON.stringify(list.slice(0, HISTORY_MAX))); return true; } catch (e) { return false; }
}

function writeHistory(list) {
  return writeHistoryTo(keepsHistory(), list);
}

// The answer as it is kept: without the five articles of the search, which are large and not needed to read it again.
function addToHistory(question, reply, replaces = null) {
  if (!HISTORY_OUTCOMES.includes(reply.outcome)) return null; // null: nothing to keep; false: it could not be kept
  if (reply.outcome === "answered" && !validClaims(reply.claims)) return null; // not a reply worth keeping
  const kept = { request_id: reply.request_id, outcome: reply.outcome, reason: reply.reason, claims: reply.claims || [], articles: [],
    question_fr: reply.question_fr, masked: reply.masked, question_masked: reply.question_masked };
  const entry = { id: reply.request_id, at: new Date().toISOString(), question, reply: kept };
  const list = loadHistory();
  if (list === null) return false;
  return writeHistory([entry, ...list.filter((other) => other.id !== entry.id && other.id !== replaces)]);
}

// The English translation of an answer, once the visitor has asked for it, goes into the entry of that answer.
// After the reply of the service: if the box that asked was removed meanwhile (the page was drawn again, for a change of language),
// the answer on the first page is drawn again from what is kept; if it is still there, the keyboard focus goes to it.
function showLate(reply, box) {
  if (box.isConnected === false) { if (last && last.reply === reply) show(); return; }
  const active = document.activeElement;
  if (active && ["textarea", "input", "select"].includes(String(active.tagName).toLowerCase())) return; // the visitor is typing: no theft of focus
  box.setAttribute("tabindex", "-1");
  box.focus();
}

// Adds fields to the reply kept for a request (the translation, or the fact that the answer is gone). False when the entry is not
// in the history or the browser refused to write.
function updateEntry(requestId, changes) {
  const list = loadHistory();
  const entry = list && list.find((other) => other.id === requestId);
  if (!entry) return false;
  Object.assign(entry.reply, changes);
  return writeHistory(list);
}

// The history page draws its entries again from what is kept, so that an entry redrawn while the request was running shows it.
function refreshHistory(saved) {
  if (saved && document.getElementById("history")) drawHistory();
}

const MONTHS = {
  fr: ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."],
  en: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
};

// "24 Nov 2026, 15:18": the month is a word, so the order of day and month cannot be misread.
function formatDate(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getDate()} ${MONTHS[lang][d.getMonth()]} ${d.getFullYear()}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function removeQuietly(persistent, key) {
  try { browserStore(persistent).removeItem(key); return true; } catch (e) { return false; }
}

// Moves the list to the device (on) or back to the tab (off). The list is written to its new place first and removed from the old
// one only when that worked, so a refusing or full storage never loses it. Returns "ok"; "failed" (nothing changed, and the copy just
// written is taken away again); or "copy-left" (unticked, but the browser refused to remove the copy on the device).
function setKeepHistory(on) {
  const current = loadHistory(); // read from the place it is in now
  if (current === null || !writeHistoryTo(on, current)) return "failed";
  try {
    if (on) browserStore(true).setItem(KEEP_KEY, "1");
    else browserStore(true).removeItem(KEEP_KEY);
  } catch (e) { return removeQuietly(on, HISTORY_KEY) ? "failed" : "copy-left"; } // the copy just written is taken away again
  return removeQuietly(!on, HISTORY_KEY) || on ? "ok" : "copy-left"; // a copy left in the tab by ticking is the tab's own memory
}

// False when the browser refused to remove one of the two copies.
function clearHistory() {
  const results = [false, true].map((persistent) => removeQuietly(persistent, HISTORY_KEY));
  return results.every(Boolean);
}

// "Show the answer: How long…": French puts a space before the colon, English does not.
function entryLabel(text, excerpt) {
  return `${text}${lang === "fr" ? " :" : ":"} ${excerpt}`;
}

// A button of an entry: its text, and for a screen reader the start of the question too, since every entry has the same buttons.
function entryButton(key, excerpt, expanded = null) {
  const button = make("button", { type: "button", class: "pill", text: t(key), "aria-label": entryLabel(t(key), excerpt) });
  if (expanded !== null) button.setAttribute("aria-expanded", String(expanded));
  return button;
}

// One entry of the list. Returns its row and its show/hide button (the one that takes the focus when a neighbour is deleted).
function historyEntry(entry, position) {
  const when = formatDate(entry.at);
  const body = make("div", { class: "hist-body", hidden: "" });
  const answered = entry.reply.outcome === "answered";
  const [show, hide] = answered ? ["history_show", "history_hide"] : ["history_show_result", "history_hide_result"]; // a refusal has no answer
  const excerpt = entry.question.length > 40 ? `${entry.question.slice(0, 40)}…` : entry.question;
  let toggle = entryButton(show, excerpt, false);
  if (openEntries.has(entry.id)) { // an entry that was open stays open when the list is drawn again (a change of language)
    fillBody(entry, body);
    body.hidden = false;
    toggle = entryButton(hide, excerpt, true);
  }
  toggle.addEventListener("click", () => {
    if (body.hidden) { fillBody(entry, body); openEntries.add(entry.id); } else openEntries.delete(entry.id);
    body.hidden = !body.hidden;
    toggle.textContent = t(body.hidden ? show : hide);
    toggle.setAttribute("aria-label", entryLabel(toggle.textContent, excerpt));
    toggle.setAttribute("aria-expanded", String(!body.hidden));
  });
  const status = make("span", { class: `hist-status ${answered ? "ok" : "none"}`, text: t(answered ? "history_answered" : "history_noanswer") });
  // the French question that was searched stays visible on the closed line: a visitor who cannot read French can still tell entries apart
  const french = entry.reply.question_fr ? make("p", { class: "count hist-fr" }, make("span", { class: "tr-label", text: t("translated") }), " ",
    make("q", { text: entry.reply.question_fr })) : "";
  const edit = entryButton("history_edit", excerpt);
  edit.addEventListener("click", () => editFromHistory(entry));
  const remove = entryButton("history_delete", excerpt);
  remove.addEventListener("click", () => {
    if (Date.now() - lastDeleteAt < 500) return; // the second click of a double click would land on the entry that slid up
    lastDeleteAt = Date.now();
    deleteEntry(entry.id);
    drawHistory(position);
  });
  const row = make("div", { class: "hist" }, make("span", { class: "tr-label", text: when }), " ", status,
    make("p", { class: "hist-q", text: entry.question }), french, make("div", { class: "hist-actions" }, toggle, edit, remove), body);
  return { row, toggle };
}

const openEntries = new Set(); // the ids of the entries the visitor has opened
let lastDeleteAt = 0;

// The inside of an opened entry: what was masked in the question, the date of the answer, then the answer or the refusal.
// An entry changed by hand or by another version of the page may have the wrong shape: it says so instead of doing nothing.
function fillBody(entry, body) {
  try {
    const kept = entry.reply;
    if (!HISTORY_OUTCOMES.includes(kept.outcome) || (kept.outcome === "answered" && !validClaims(kept.claims))) {
      throw new Error("not a reply this page keeps");
    }
    const key = entry.reply.outcome === "answered" ? "history_dated" : "history_dated_result";
    const date = formatDate(entry.at);
    const dated = date ? make("p", { class: "count", text: t(key, { date }) }) : null;
    body.replaceChildren(...[maskedNotice(entry.reply), dated, replyNode({ ...entry.reply, at: entry.at }, 200, null, true)].filter(Boolean));
  } catch (e) {
    body.replaceChildren(make("p", { class: "status problem", text: t("history_unreadable") }));
  }
}

function deleteEntry(id) {
  openEntries.delete(id);
  const list = loadHistory();
  if (list !== null) writeHistory(list.filter((entry) => entry.id !== id));
}

// "Edit this question": the question box of the first page gets the old text, ready to change and to send. Nothing is sent
// from here. The text goes through the memory of the tab (it never reaches the service).
const PREFILL_KEY = "prefill";
const PREFILL_ENGLISH_KEY = "prefill_english";

// A question that was translated was written in English: the first page then offers the translation again.
function editFromHistory(entry) {
  try {
    browserStore(false).setItem(PREFILL_KEY, entry.question);
    browserStore(false).setItem(PREFILL_ENGLISH_KEY, entry.reply.question_fr ? "1" : "0");
  } catch (e) { /* refused: the page opens with an empty box */ }
  window.location.href = "/";
}

function takePrefill() {
  try {
    const store = browserStore(false);
    const text = store.getItem(PREFILL_KEY);
    const english = store.getItem(PREFILL_ENGLISH_KEY) === "1";
    store.removeItem(PREFILL_KEY);
    store.removeItem(PREFILL_ENGLISH_KEY);
    return { text: typeof text === "string" ? text : "", english };
  } catch (e) { return { text: "", english: false }; }
}

// `focusAt`: the position of an entry that was just deleted. The focus goes to the entry now at that place (or the last one, or
// the tick box when the list is empty), so that a keyboard user is not sent back to the top of the page.
function drawHistory(focusAt = null) {
  const root = document.getElementById("history");
  if (!root) return;
  const list = readHistory();
  const state = storageState();
  if (state === "blocked") { root.replaceChildren(make("p", { class: "status problem", text: t("history_blocked") })); return; }
  const empty = `${t("history_empty")}${keepsHistory() ? "" : ` ${t("history_empty_tab")}`}`;
  const rows = list.map(historyEntry);
  const confirm = document.getElementById("confirm");
  if (confirm && !rows.length) confirm.hidden = true; // nothing left to erase
  const hint = rows.length ? ` ${t("history_full_hint")}` : "";
  const full = state === "full" ? [make("p", { class: "status problem", text: `${t("history_full")}${hint}` })] : [];
  root.replaceChildren(...full, ...(rows.length ? rows.map((r) => r.row) : [make("p", { class: "count", text: empty })]));
  if (focusAt !== null) (rows.length ? rows[Math.min(focusAt, rows.length - 1)].toggle : document.getElementById("keep")).focus();
}

function setupHistory() {
  const keep = document.getElementById("keep");
  keep.checked = keepsHistory();
  const keepFailed = document.getElementById("keep-failed");
  const unkeepFailed = document.getElementById("unkeep-failed");
  keep.addEventListener("change", () => {
    const wanted = keep.checked;
    const result = setKeepHistory(wanted);
    keepFailed.hidden = !(wanted && result === "failed");
    unkeepFailed.hidden = !(result === "copy-left" || (!wanted && result === "failed"));
    keep.checked = keepsHistory(); // the box shows what really happened
    drawHistory();
  });
  // Another tab changed the kept list or the tick: this tab shows it too (the lists are read again before every write anyway).
  // Only these two keys: the page's own storage test writes another key, and answering that would make two tabs redraw each other forever.
  window.addEventListener("storage", (event) => {
    if (event.key && event.key !== HISTORY_KEY && event.key !== KEEP_KEY) return;
    keep.checked = keepsHistory();
    drawHistory();
  });
  // erasing everything asks first, with a question of its own: the button text is never swapped, so a change of language cannot
  // leave the page in a half-asked state
  // The focus goes to "Cancel" (the safe choice) when the question opens, and back to the Erase button when it closes.
  const confirm = document.getElementById("confirm");
  const clear = document.getElementById("clear");
  clear.addEventListener("click", () => {
    if (!readHistory().length) return; // nothing to erase: no question
    confirm.hidden = false;
    document.getElementById("confirm-no").focus();
  });
  document.getElementById("confirm-no").addEventListener("click", () => { confirm.hidden = true; clear.focus(); });
  const eraseFailed = document.getElementById("erase-failed");
  document.getElementById("confirm-yes").addEventListener("click", () => {
    eraseFailed.hidden = clearHistory();
    confirm.hidden = true;
    drawHistory();
    clear.focus();
  });
  drawHistory();
}
