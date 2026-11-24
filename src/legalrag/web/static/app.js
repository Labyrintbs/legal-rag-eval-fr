// The demo pages (step 0f, part 4): the question box, the example cards, the answer with its sources, the vote, and the
// FR/EN switch of the page text. No framework. Everything that comes from the server is written with textContent, never
// as HTML. The French text is in the HTML files, the English text in texts_en.js (loaded first, defines EN); this file
// holds the messages it builds itself.
"use strict";

const T = {
  fr: {
    history_empty: "Aucune question pour le moment.", history_show: "Afficher la réponse", history_hide: "Masquer la réponse",
    history_show_result: "Afficher le résultat", history_hide_result: "Masquer le résultat", history_answered: "Répondu", history_noanswer: "Sans réponse",
    history_edit: "Modifier cette question", history_delete: "Supprimer cette entrée",
    history_empty_tab: "Cet onglet n'a pas de liste gardée : cochez la case ci-dessus pour garder la vôtre.",
    history_blocked: "Votre navigateur ne permet pas de garder l'historique : la liste restera vide.",
    history_full: "Le navigateur refuse d'écrire (stockage plein ou bloqué) : les nouvelles questions ne seront pas gardées. Supprimez des entrées pour faire de la place.",
    history_unreadable: "Cette entrée est illisible. Vous pouvez la supprimer.",
    history_dated: "Réponse du {date} : la loi a pu changer depuis.", history_dated_result: "Résultat du {date} : la loi a pu changer depuis.",
    busy: "Une autre question est déjà en cours depuis votre connexion : attendez sa réponse.",
    failed: "Le service a rencontré un problème. Réessayez dans un instant.",
    loaded: "Question reprise de votre historique : modifiez-la si besoin, puis envoyez-la.",
    translate_gone: "Le service ne garde plus cette réponse (7 jours) : la traduction n'est plus possible.",
    not_saved: "Cette réponse n'a pas pu être gardée dans l'historique : le navigateur refuse ou n'a plus de place.",
    searching: "Recherche en cours…", translating: "Traduction de la question, puis recherche…", translated: "Question traduite en français :", edit_question: "Modifier", ask_again: "Poser à nouveau",
    show_english: "Traduction anglaise de cette réponse · English translation of this answer", translating_answer: "Traduction en cours…",
    english_label: "Machine translation into English (the French text is authoritative) · Traduction automatique en anglais (le texte français fait foi)",
    translate_failed: "La traduction n'a pas pu être faite. · The translation could not be made.", empty: "Écrivez une question.", network: "Le service ne répond pas. Réessayez dans un instant.",
    invalid: "La question doit avoir entre 1 et 500 caractères.", limited: "Trop de demandes de votre part. Réessayez dans {n} s.",
    unavailable: "Le service est momentanément indisponible", upstream: "Le modèle n'a pas répondu. Les articles trouvés sont montrés ci-dessous.",
    noanswer: "Pas de réponse : les textes de ce service ne permettent pas de répondre.", weak: "Pas de réponse : rien de suffisamment proche n'a été trouvé dans les textes.",
    scope: "Ce service ne contient que le Code du travail et le RGPD (pas les conventions collectives, pas la jurisprudence).",
    next: "Pour un cas précis, consultez un avocat, l'inspection du travail ou Légifrance.", why: "Raison donnée par le service :",
    found_weak: "Les {n} articles les plus proches (peu pertinents ici)", answer: "Réponse", where: "Où dans la loi ?",
    stored: "réponse déjà préparée", cited: "Passages cités", found: "Les {n} articles les plus proches de votre question",
    found_hint: "La réponse est écrite à partir de ces articles seulement, du plus proche au moins proche.",
    read: "Lire l'article", on: "sur", useful: "Cette réponse est-elle utile ?", thanks: "Merci, votre avis est enregistré.",
    kind: "Qu'est-ce qui ne va pas ? (facultatif)", wrong_answer: "La réponse est fausse", wrong_citation: "Une citation ne correspond pas",
    missing_article: "Un article manque", other: "Autre", comment: "Un commentaire ? (facultatif, 500 caractères au plus)", send: "Envoyer",
    vote_failed: "Le vote n'a pas pu être enregistré.", vote_limited: "Trop de votes d'affilée, réessayez dans un instant.",
    up: "Réponse utile", down: "Réponse pas utile", src_ct: "Code du travail", src_gdpr: "RGPD", src_none: "Hors des textes",
    masked_intro: "Pour protéger vos données, nous avons masqué dans votre question : {what}. La question utilisée est : « {question} ». Les noms et les adresses postales ne sont pas détectés : évitez de les écrire.",
    pii_email: "une adresse e-mail", pii_phone: "un numéro de téléphone", pii_iban: "un IBAN", pii_card: "un numéro de carte bancaire",
    pii_nir: "un numéro de sécurité sociale", pii_birth: "une date de naissance",
  },
  en: {
    history_empty: "No question yet.", history_show: "Show the answer", history_hide: "Hide the answer",
    history_show_result: "Show the result", history_hide_result: "Hide the result", history_answered: "Answered", history_noanswer: "No answer",
    history_edit: "Edit this question", history_delete: "Delete this entry",
    history_empty_tab: "This tab has no kept list: tick the box above to keep yours.",
    history_blocked: "Your browser does not allow keeping the history: the list will stay empty.",
    history_full: "The browser refuses to write (storage full or blocked): new questions will not be kept. Delete entries to make room.",
    history_unreadable: "This entry cannot be read. You can delete it.",
    history_dated: "Answer of {date}: the law may have changed since.", history_dated_result: "Result of {date}: the law may have changed since.",
    busy: "Another question is already in progress from your connection: wait for its answer.",
    failed: "The service had a problem. Try again in a moment.",
    loaded: "Question taken from your history: change it if you wish, then send it.",
    translate_gone: "The service no longer holds this answer (7 days): it can no longer be translated.",
    not_saved: "This answer could not be kept in the history: the browser refuses or is full.",
    searching: "Searching…", translating: "Translating the question, then searching…", translated: "Question translated into French:", edit_question: "Edit", ask_again: "Ask again",
    show_english: "English translation of this answer", translating_answer: "Translating…",
    english_label: "Machine translation into English (the French text is authoritative)", translate_failed: "The translation could not be made.", empty: "Write a question.", network: "The service does not answer. Try again in a moment.",
    invalid: "The question must be 1 to 500 characters long.", limited: "Too many requests from you. Try again in {n} s.",
    unavailable: "The service is temporarily unavailable", upstream: "The model did not answer. The articles found are shown below.",
    noanswer: "No answer: the texts of this service do not allow one.", weak: "No answer: nothing close enough was found in the texts.",
    scope: "This service contains only the French labour code and the GDPR (no collective agreements, no case law).",
    next: "For a specific case, consult a lawyer, the labour inspectorate or Légifrance.", why: "Reason given by the service (in French):",
    found_weak: "The {n} closest articles (not very relevant here; in French)", answer: "Answer (in French)", where: "Where in the law?",
    stored: "ready-made answer", cited: "Cited passages (in French)", found: "The {n} articles closest to your question (in French)",
    found_hint: "The answer is written from these articles only, from the closest to the least close.",
    read: "Read the article", on: "on", useful: "Was this answer useful?", thanks: "Thank you, your opinion is saved.",
    kind: "What is wrong? (optional)", wrong_answer: "The answer is wrong", wrong_citation: "A citation does not match",
    missing_article: "An article is missing", other: "Other", comment: "A comment? (optional, 500 characters at most)", send: "Send",
    vote_failed: "The vote could not be saved.", vote_limited: "Too many votes in a row, try again in a moment.",
    up: "Useful answer", down: "Answer not useful", src_ct: "Labour code", src_gdpr: "GDPR", src_none: "Outside the texts",
    masked_intro: "To protect your data, we masked in your question: {what}. The question used is: “{question}”. Names and postal addresses are not detected: avoid writing them.",
    pii_email: "an e-mail address", pii_phone: "a telephone number", pii_iban: "an IBAN", pii_card: "a bank card number",
    pii_nir: "a social security number", pii_birth: "a date of birth",
  },
};

const ENGLISH_WORDS = new Set(["the", "is", "are", "was", "what", "which", "how", "can", "could", "does", "do", "did", "my", "your",
  "you", "i", "of", "with", "from", "have", "has", "if", "when", "there", "would", "should", "must", "and", "to", "it"]);
const FRENCH_WORDS = new Set(["le", "la", "les", "est", "que", "quel", "quelle", "quels", "mon", "ma", "mes", "je", "de", "du", "des", "un",
  "une", "et", "pour", "puis", "peut", "dans", "sur", "par", "au", "aux", "qui", "ou", "il", "elle", "pas"]);

let lang = "fr";
try { lang = localStorage.getItem("lang") === "en" ? "en" : "fr"; } catch (e) { /* no storage: French */ }
let examples = [];
let last = null; // {reply, status, retryAfter}: kept to draw it again when the language changes

const t = (key, values = {}) => (T[lang][key] ?? key).replace(/\{(\w+)\}/g, (_, name) => values[name]); // a missing text shows its key, not an error

function make(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(props)) {
    if (name === "text") node.textContent = value;
    else if (name === "class") node.className = value;
    else node.setAttribute(name, value);
  }
  node.append(...children);
  return node;
}

function applyLanguage() {
  document.documentElement.lang = lang;
  for (const node of document.querySelectorAll("[data-i18n]")) {
    if (node.dataset.fr === undefined) node.dataset.fr = node.innerHTML; // the French text of the HTML file
    node.innerHTML = lang === "en" && EN[node.dataset.i18n] ? EN[node.dataset.i18n] : node.dataset.fr;
  }
  for (const node of document.querySelectorAll("[data-i18n-placeholder]")) {
    if (node.dataset.fr === undefined) node.dataset.fr = node.placeholder;
    node.placeholder = lang === "en" ? EN[node.dataset.i18nPlaceholder] : node.dataset.fr;
  }
  // the page title, the description for search engines and the labels for screen readers follow the language too
  for (const node of document.querySelectorAll("[data-i18n-content]")) {
    if (node.dataset.frContent === undefined) node.dataset.frContent = node.getAttribute("content");
    node.setAttribute("content", lang === "en" ? EN[node.dataset.i18nContent] : node.dataset.frContent);
  }
  for (const node of document.querySelectorAll("[data-i18n-aria]")) {
    if (node.dataset.frAria === undefined) node.dataset.frAria = node.getAttribute("aria-label");
    node.setAttribute("aria-label", lang === "en" ? EN[node.dataset.i18nAria] : node.dataset.frAria);
  }
  for (const button of document.querySelectorAll("[data-lang]")) button.setAttribute("aria-pressed", String(button.dataset.lang === lang));
  const note = document.getElementById("lang-note"); // the English page says that the questions and answers are French
  if (note) note.hidden = lang !== "en";
}

// English words win over French ones; a short question ("Probation period?") has too few words for that, so on the English
// page it is offered the translation as long as nothing in it looks French (no French word, no accented letter).
function offersTranslation(text) {
  if (looksEnglish(text)) return true;
  const words = text.toLowerCase().match(/[a-zàâçéèêëîïôûùüÿœ']+/g) || [];
  return lang === "en" && words.length > 0 && !/[àâçéèêëîïôûùüÿœ]/.test(text.toLowerCase()) && !words.some((w) => FRENCH_WORDS.has(w));
}

function looksEnglish(text) {
  const words = text.toLowerCase().match(/[a-zàâçéèêëîïôûùüÿœ']+/g) || [];
  const english = words.filter((w) => ENGLISH_WORDS.has(w)).length;
  const french = words.filter((w) => FRENCH_WORDS.has(w)).length;
  return english >= 2 && english > french;
}

// The labels of the GDPR are "art 17" and "rct 47" (corpus/labels.py); the Code du travail ones are numbers like "L1221-19".
const sourceOf = (label) => (/^(art|rct) /.test(label) ? "gdpr" : "ct");
const tag = (kind) => make("em", { class: `tag ${kind}`, text: t(`src_${kind}`) });

function sourceSite(url) {
  if (url.includes("legifrance")) return "Légifrance";
  if (url.includes("eur-lex")) return "EUR-Lex";
  return "";
}

function link(url) {
  const site = sourceSite(url);
  // Only an https link is written: a stored reply (the history can be edited in the browser) cannot add a link that runs code.
  return make("a", { href: /^https:\/\//.test(url) ? url : "#", rel: "noopener", text: t("read") + (site ? ` ${t("on")} ${site}` : "") });
}

// The tag with the name of a source is written the first time that source appears in a list; the coloured bar on every item.
function firstTag(seen, kind) {
  if (seen.has(kind)) return "";
  seen.add(kind);
  return tag(kind);
}

// Where the article is in the code: the two deepest levels, and the whole path behind "Where in the code?".
function where(path) {
  const levels = path.split(" > ").filter(Boolean);
  if (!levels.length) return "";
  const short = make("div", { class: "where", text: levels.slice(-2).join(" › ") });
  if (levels.length <= 2) return short;
  return make("div", {}, short, make("details", { class: "fullpath" }, make("summary", { text: t("where") }),
    make("p", { class: "where", text: levels.join(" › ") })));
}

function foundArticles(articles, titleKey = "found") {
  if (!articles.length) return null;
  const list = make("ul", { class: "found" });
  const seen = new Set();
  for (const a of articles) {
    const kind = sourceOf(a.label);
    const text = a.text.length > 320 ? a.text.slice(0, 320) + "…" : a.text;
    // the same parts as a cited passage (label, source tag, place, text, link); the text is an excerpt, not a quotation
    list.append(make("li", { class: kind }, make("b", { text: a.label }), " ", firstTag(seen, kind), where(a.section_path),
      make("div", { class: "excerpt", text }), link(a.url)));
  }
  return make("details", {}, make("summary", { text: t(titleKey, { n: articles.length }) }), make("p", { class: "count", text: t("found_hint") }), list);
}

async function sendVote(requestId, value, kind, comment) {
  const body = { request_id: requestId, value };
  if (kind) body.kind = kind;
  if (comment) body.comment = comment;
  const response = await fetch("/feedback", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  return response.status;
}

function voteBox(requestId) {
  const message = make("p", { class: "count", role: "status" });
  const form = make("div", { class: "form", hidden: "" });
  const kind = make("select", { "aria-label": t("kind") }, make("option", { value: "", text: t("kind") }),
    ...["wrong_answer", "wrong_citation", "missing_article", "other"].map((k) => make("option", { value: k, text: t(k) })));
  const comment = make("textarea", { maxlength: "500", placeholder: t("comment"), "aria-label": t("comment") });
  const send = make("button", { type: "button", class: "send", text: t("send") });
  form.append(kind, comment, send);
  const up = make("button", { type: "button", class: "thumb", "aria-pressed": "false", "aria-label": t("up"), text: "👍" });
  const down = make("button", { type: "button", class: "thumb", "aria-pressed": "false", "aria-label": t("down"), text: "👎" });
  let value = 0;

  async function submit(extra) {
    const status = await sendVote(requestId, value, extra && kind.value, extra && comment.value.trim());
    message.textContent = status === 200 ? t("thanks") : status === 429 ? t("vote_limited") : t("vote_failed");
  }
  function vote(chosen, button, other) {
    value = chosen;
    button.setAttribute("aria-pressed", "true");
    other.setAttribute("aria-pressed", "false");
    kind.hidden = chosen !== -1;
    form.hidden = false;
    submit(false);
  }
  up.addEventListener("click", () => vote(1, up, down));
  down.addEventListener("click", () => vote(-1, down, up));
  send.addEventListener("click", () => submit(true));
  return make("div", { class: "vote" }, make("div", { class: "buttons" }, make("span", { text: t("useful") }), up, down), form, message);
}

function answerCard(reply, history = false) {
  const numbers = new Map(); // one number per distinct cited passage
  const seen = new Set(); // sources whose tag was written
  const shown = new Set(); // articles whose place was written
  const p = make("p", { class: "claim" }); // one paragraph: each sentence is followed by the numbers of its citations
  const claims = make("div", { class: "claims" }, p);
  const sources = make("div", { class: "sources" }, make("h3", { class: "count", text: t("cited") }));
  for (const claim of reply.claims) {
    p.append(claim.text);
    for (const c of claim.citations) {
      const key = `${c.label}|${c.units.join(",")}`;
      if (!numbers.has(key)) {
        numbers.set(key, numbers.size + 1);
        const kind = sourceOf(c.label);
        const place = shown.has(c.label) ? "" : where(c.section_path); // the place of an article once, not for each passage
        shown.add(c.label);
        sources.append(make("div", { class: `src ${kind}` }, make("b", { text: `[${numbers.size}] ${c.label}` }), " ", firstTag(seen, kind),
          place, make("blockquote", { text: c.passage }), link(c.url)));
      }
      p.append(make("sup", { class: "cite", text: String(numbers.get(key)) }));
    }
    p.append(" ");
  }
  const label = make("h2", { class: "label", text: t("answer") });
  if (reply.cached && !history) label.append(make("span", { class: "badge", text: t("stored") })); // days later it would mean nothing
  if (history) return make("div", { class: "answer" }, label, claims, englishBlock(reply), sources); // no vote, no list of articles
  return make("div", { class: "answer" }, label, claims, englishBlock(reply), sources, foundArticles(reply.articles) || "", voteBox(reply.request_id));
}

function problemCard(message, reply, history = false) {
  const box = make("div", { class: "status problem" }, make("div", { text: message }));
  // the reasons of the service are French sentences: the English page has its own message above and does not repeat them
  if (reply && reply.reason && lang === "fr") box.append(make("div", { class: "count", text: reply.reason }));
  const found = reply && foundArticles(reply.articles || []); // an error body such as {"detail": "..."} has no list of articles
  if (found) box.append(found);
  if (reply && reply.request_id && !history && !reply.busy) box.append(voteBox(reply.request_id)); // a busy reply was never answered
  return box;
}

// A reply with no answer: what happened, what the service covers, the reason it gave, what to do next; the articles
// that the search found stay closed, since they are often not relevant to the question.
function refusalCard(message, reply, history = false) {
  const box = make("div", { class: "status problem" }, make("p", { class: "refusal", text: message }), make("p", { text: t("scope") }));
  if (reply.reason) box.append(make("p", { class: "count", text: `${t("why")} ${reply.reason}` }));
  box.append(make("p", { text: t("next") }));
  const found = foundArticles(reply.articles || [], "found_weak");
  if (found) box.append(found);
  if (reply.request_id && !history) box.append(voteBox(reply.request_id));
  return box;
}

// Tells the visitor what the personal-data filter masked in the question, and the question that was really used.
function maskedNotice(reply) {
  if (!reply || !Array.isArray(reply.masked) || !reply.masked.length) return null;
  const what = [...new Set(reply.masked)].map((kind) => t(`pii_${kind}`)).join(", ");
  return make("p", { class: "notice", text: t("masked_intro", { what, question: reply.question_masked }) });
}

function show() {
  const result = document.getElementById("result");
  if (!result) return;
  result.replaceChildren();
  if (!last) return;
  drawReply();
  const line = translatedLine(last.reply);
  if (line) result.prepend(line);
  const note = last.status === 200 ? maskedNotice(last.reply) : null; // a refused request used no question
  if (note) result.prepend(note);
  if (last.notSaved) result.append(make("p", { class: "count", text: t("not_saved") }));
}

// When the visitor asked for a translation: the French question that was really searched.
function translatedLine(reply) {
  if (!reply || !reply.question_fr) return null;
  // The French question is shown as it was used. "Modifier" turns it into a field of its own, with a button that stays off
  // until the text has changed; the English text stays in the box above.
  const shown = make("q", { text: reply.question_fr });
  const edit = make("button", { type: "button", class: "linklike", text: t("edit_question") });
  edit.addEventListener("click", () => {
    const field = make("textarea", { class: "tr-field", rows: "2", maxlength: "500", "aria-label": t("translated") });
    field.value = reply.question_fr;
    const again = make("button", { type: "button", class: "send", text: t("ask_again"), disabled: "" });
    field.addEventListener("input", () => { again.disabled = !field.value.trim() || field.value.trim() === reply.question_fr; });
    again.addEventListener("click", () => ask(field.value.trim(), false, true));
    shown.replaceWith(field);
    edit.replaceWith(again);
    field.focus();
  });
  return make("div", { class: "tr-line" }, make("span", { class: "tr-label", text: t("translated") }), shown, edit);
}

// The sentences of a translation with their citation numbers as small tags, like the French answer.
function withMarkers(text) {
  const paragraph = make("p", { class: "claim en" });
  for (const part of text.split(/(\[\d+\])/)) {
    const mark = part.match(/^\[(\d+)\]$/);
    paragraph.append(mark ? make("sup", { class: "cite", text: mark[1] }) : part);
  }
  return paragraph;
}

// The English translation of an answer, on request, for a visitor who asked in English or has the page in English.
function englishBlock(reply) {
  if (reply.outcome !== "answered" || !(reply.question_fr || lang === "en")) return "";
  if (reply.english) return savedEnglish(reply); // already asked for: shown again after a change of language, never requested twice
  const box = make("div", { class: "en-answer" });
  if (reply.english_gone) { // the service no longer holds the answer: asking again would change nothing
    box.append(make("span", { class: "count", text: t("translate_gone") }));
    return box;
  }
  const button = make("button", { type: "button", class: "pill", text: t("show_english") });
  button.addEventListener("click", () => askEnglish(reply, box, button));
  box.append(button);
  return box;
}

// One request for the translation of an answer. The note of an earlier try is removed first, so that notes do not pile up.
async function askEnglish(reply, box, button) {
  button.disabled = true;
  if (button.note) button.note.remove();
  button.note = make("span", { class: "count", text: ` ${t("translating_answer")}` });
  box.append(button.note);
  let message = t("translate_failed");
  try {
    const response = await fetch("/translate-answer", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_id: reply.request_id }) });
    const data = await response.json().catch(() => ({}));
    if (response.status === 200 && typeof data.english === "string") {
      box.replaceChildren(make("span", { class: "tr-label", text: t("english_label") }), withMarkers(data.english));
      reply.english = data.english;
      refreshHistory(updateEntry(reply.request_id, { english: data.english }));
      return;
    }
    if (response.status === 429) message = t("limited", { n: Number(response.headers.get("Retry-After")) || 60 });
    if (response.status === 410 || response.status === 404) { // the service keeps an answer 7 days; the button stays off, also after a redraw
      button.note.textContent = ` ${t("translate_gone")}`;
      reply.english_gone = true;
      refreshHistory(updateEntry(reply.request_id, { english_gone: true }));
      return;
    }
  } catch (e) { /* the message below tells */ }
  button.disabled = false;
  button.note.textContent = ` ${message}`;
}

// The English translation kept in the history: shown when the visitor asked for it, never requested again (the service
// keeps an answer 7 days only).
function savedEnglish(reply) {
  if (!reply.english) return "";
  return make("div", { class: "en-answer" }, make("span", { class: "tr-label", text: t("english_label") }), withMarkers(reply.english));
}

// What a reply looks like. `history`: drawn from the history, where the vote and the list of articles are not offered.
function replyNode(reply, status, retryAfter, history = false) {
  if (status === 0) return make("div", { class: "status problem", text: t("network") });
  if (status === 422) return make("div", { class: "status problem", text: t("invalid") });
  if (status === 429 && reply && reply.busy) return problemCard(t("busy"), { ...reply, reason: null }, history);
  if (status === 429) return problemCard(t("limited", { n: retryAfter || (reply && reply.retry_after) || 60 }), reply, history);
  if (status === 503) return problemCard(`${t("unavailable")}.`, reply, history);
  if (status === 502) return problemCard(t("upstream"), reply, history);
  if (status !== 200 || !reply) return problemCard(t("failed"), null, history); // 500, 504, 404...: never read as a refusal of the model
  if (reply.outcome === "answered") return answerCard(reply, history);
  if (reply.outcome === "refused_weak_retrieval") return refusalCard(t("weak"), { ...reply, reason: null }, history);
  return refusalCard(t("noanswer"), reply, history);
}

function drawReply() {
  const { reply, status, retryAfter } = last;
  const node = replyNode(reply, status, retryAfter);
  if (node) document.getElementById("result").append(node);
}

// The answer area is just under the question box; bring it into view, since the visitor may have clicked a card far below.
function showResultArea() {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.getElementById("result").scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
}

// `fromField`: the question is the French text of the translated-question field (kept on screen, since it is what was searched).
async function ask(question, translate = false, fromField = false) {
  const go = document.getElementById("go");
  const result = document.getElementById("result");
  result.replaceChildren(make("div", { class: "status", text: t(translate ? "translating" : "searching") }));
  showResultArea();
  go.disabled = true;
  // Asked again from the French line: the entry keeps the English the visitor wrote, and replaces the one of the first try.
  const previous = last && last.reply ? last.reply.request_id : null;
  const typed = fromField && last && last.original ? last.original : question;
  try {
    const response = await fetch("/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, translate }) });
    let reply = null;
    try { reply = await response.json(); } catch (e) { /* not JSON: the status tells */ }
    if (reply !== null && typeof reply !== "object") reply = null; // a text or a number is no reply
    if (fromField && reply && response.status !== 422) reply.question_fr = question;
    last = { reply: response.status === 422 ? null : reply, status: response.status, retryAfter: Number(response.headers.get("Retry-After")) || null,
      original: typed };
    if (response.status === 200 && reply) last.notSaved = addToHistory(typed, reply, fromField ? previous : null) === false;
  } catch (e) {
    last = { reply: null, status: 0, original: typed };
  } finally {
    go.disabled = false;
  }
  show();
  showResultArea();
}

function drawExamples() {
  const cards = document.getElementById("cards");
  if (!cards) return;
  cards.replaceChildren(...examples.map((e) => {
    const card = make("button", { type: "button", class: "card" }, tag(e.source), make("b", { text: e.label[lang] || e.label.fr }),
      make("span", { text: e.question }), lang === "en" && e.question_en ? make("span", { class: "gloss", text: `(${e.question_en})` }) : "");
    card.addEventListener("click", () => {
      const box = document.getElementById("question");
      box.value = e.question;
      updateCount();
      ask(e.question);
    });
    return card;
  }));
}

function updateCount() {
  const box = document.getElementById("question");
  document.getElementById("count").textContent = `${box.value.length} / 500`;
  document.getElementById("english").hidden = !offersTranslation(box.value);
}

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

function readHistory() {
  try {
    const list = JSON.parse(browserStore(keepsHistory()).getItem(HISTORY_KEY) || "[]");
    if (!Array.isArray(list)) return [];
    const seen = new Set(); // two entries with one id (a list edited by hand) would open and be deleted together
    return list.filter((entry) => {
      const fit = entry && typeof entry.id === "string" && typeof entry.question === "string" && entry.reply && typeof entry.reply === "object"
        && !seen.has(entry.id);
      if (fit) seen.add(entry.id);
      return fit;
    });
  } catch (e) { return []; }
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
  const kept = { request_id: reply.request_id, outcome: reply.outcome, reason: reply.reason, claims: reply.claims || [], articles: [],
    question_fr: reply.question_fr, masked: reply.masked, question_masked: reply.question_masked };
  const entry = { id: reply.request_id, at: new Date().toISOString(), question, reply: kept };
  return writeHistory([entry, ...readHistory().filter((other) => other.id !== entry.id && other.id !== replaces)]);
}

// The English translation of an answer, once the visitor has asked for it, goes into the entry of that answer.
// Adds fields to the reply kept for a request (the translation, or the fact that the answer is gone). False when the entry is not
// in the history or the browser refused to write.
function updateEntry(requestId, changes) {
  const list = readHistory();
  const entry = list.find((other) => other.id === requestId);
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

// Moves the list to the device (on) or back to the tab (off). The list is written to its new place first and removed from the old
// one only when that worked, so a refusing or full storage never loses it. False when nothing could be done.
function setKeepHistory(on) {
  const current = readHistory(); // read from the place it is in now
  if (!writeHistoryTo(on, current)) return false;
  try {
    if (on) browserStore(true).setItem(KEEP_KEY, "1");
    else browserStore(true).removeItem(KEEP_KEY);
    browserStore(!on).removeItem(HISTORY_KEY);
  } catch (e) { return false; }
  return true;
}

function clearHistory() {
  for (const persistent of [false, true]) {
    try { browserStore(persistent).removeItem(HISTORY_KEY); } catch (e) { /* refused */ }
  }
}

// A button of an entry: its text, and for a screen reader the start of the question too, since every entry has the same buttons.
function entryButton(key, excerpt, expanded = null) {
  const button = make("button", { type: "button", class: "pill", text: t(key), "aria-label": `${t(key)} : ${excerpt}` });
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
    toggle.setAttribute("aria-label", `${toggle.textContent} : ${excerpt}`);
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
    const key = entry.reply.outcome === "answered" ? "history_dated" : "history_dated_result";
    const date = formatDate(entry.at);
    const dated = date ? make("p", { class: "count", text: t(key, { date }) }) : null;
    body.replaceChildren(...[maskedNotice(entry.reply), dated, replyNode(entry.reply, 200, null, true)].filter(Boolean));
  } catch (e) {
    body.replaceChildren(make("p", { class: "status problem", text: t("history_unreadable") }));
  }
}

function deleteEntry(id) {
  openEntries.delete(id);
  writeHistory(readHistory().filter((entry) => entry.id !== id));
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
  const full = state === "full" ? [make("p", { class: "status problem", text: t("history_full") })] : [];
  root.replaceChildren(...full, ...(rows.length ? rows.map((r) => r.row) : [make("p", { class: "count", text: empty })]));
  if (focusAt !== null) (rows.length ? rows[Math.min(focusAt, rows.length - 1)].toggle : document.getElementById("keep")).focus();
}

function setupHistory() {
  const keep = document.getElementById("keep");
  keep.checked = keepsHistory();
  const keepFailed = document.getElementById("keep-failed");
  keep.addEventListener("change", () => {
    keepFailed.hidden = setKeepHistory(keep.checked);
    keep.checked = keepsHistory(); // the box shows what really happened
    drawHistory();
  });
  // Another tab changed the kept list or the tick: this tab shows it too (the lists are read again before every write anyway).
  window.addEventListener("storage", () => { keep.checked = keepsHistory(); drawHistory(); });
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
  document.getElementById("confirm-yes").addEventListener("click", () => { clearHistory(); confirm.hidden = true; drawHistory(); clear.focus(); });
  drawHistory();
}

// The contact address is never written in the page: it is put together when the visitor clicks, so that programs
// which read pages for addresses do not find it.
function openMail(event) {
  const link = event.currentTarget;
  event.preventDefault();
  window.location.href = `mailto:${link.dataset.user}@${link.dataset.host}`;
}

function setup() {
  applyLanguage();
  for (const link of document.querySelectorAll("a.mail")) link.addEventListener("click", openMail);
  for (const button of document.querySelectorAll("[data-lang]")) {
    button.addEventListener("click", () => {
      lang = button.dataset.lang;
      try { localStorage.setItem("lang", lang); } catch (e) { /* ignore */ }
      applyLanguage();
      drawExamples();
      drawHistory();
      show();
      if (document.getElementById("question")) updateCount(); // the offer of the translation depends on the page language
    });
  }
  if (document.getElementById("history")) setupHistory();
  const form = document.getElementById("ask");
  if (!form) return; // the other pages
  const box = document.getElementById("question");
  const prefill = takePrefill();
  if (prefill.text) {
    box.value = prefill.text.slice(0, 500);
    updateCount();
    if (prefill.english) document.getElementById("english").hidden = false;
    document.getElementById("result").replaceChildren(make("div", { class: "status", text: t("loaded") }));
    box.focus();
  }
  box.addEventListener("input", updateCount);
  box.addEventListener("keydown", (event) => { if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) form.requestSubmit(); });
  document.getElementById("translate").addEventListener("click", () => {
    const question = box.value.trim();
    if (question) ask(question, true);
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const question = box.value.trim();
    if (question) ask(question);
    else document.getElementById("result").replaceChildren(make("div", { class: "status problem", text: t("empty") }));
  });
  fetch("/examples").then((r) => r.json()).then((list) => { examples = list; drawExamples(); }).catch(() => { /* no examples: the box still works */ });
}

setup();
