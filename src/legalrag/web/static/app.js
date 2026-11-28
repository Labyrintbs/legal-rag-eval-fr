// The demo pages (step 0f, part 4): the question box, the example cards, the answer with its sources, the vote, and the
// FR/EN switch of the page text. No framework. Everything that comes from the server is written with textContent, never
// as HTML. The French text is in the HTML files, the English text in texts_en.js (loaded first, defines EN); this file
// holds the messages it builds itself. The history is in history.js and the contact link in mail.js, loaded before this
// file (which calls `setup()` at its end).
"use strict";

const T = {
  fr: {
    history_empty: "Aucune question pour le moment.", history_show: "Afficher la réponse", history_hide: "Masquer la réponse",
    history_show_result: "Afficher le résultat", history_hide_result: "Masquer le résultat", history_answered: "Répondu", history_noanswer: "Sans réponse",
    history_edit: "Modifier cette question", history_delete: "Supprimer cette entrée",
    history_empty_tab: "La liste de cet onglet disparaît quand vous le fermez : cochez la case ci-dessus pour la garder sur cet appareil.",
    history_blocked: "Votre navigateur ne permet pas de garder l'historique : la liste restera vide.",
    history_full: "Le navigateur refuse d'écrire (stockage plein ou bloqué) : les nouvelles questions ne seront pas gardées.",
    history_full_hint: "Supprimez des entrées pour faire de la place.",
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
    invalid: "La question doit avoir entre 1 et 500 caractères.", limited: "Trop de demandes de votre part. Réessayez dans {n}.",
    unavailable: "Le service est momentanément indisponible", upstream: "Le modèle n'a pas répondu. Les articles trouvés sont montrés ci-dessous.",
    upstream_none: "Le modèle n'a pas répondu. Réessayez dans un instant.",
    translate_question_failed: "La traduction de votre question a échoué. Réessayez, ou écrivez-la en français.",
    translate_unknown: "Le service n'a pas gardé cette réponse : la traduction n'est pas possible.",
    pii_other: "des données personnelles",
    noanswer: "Pas de réponse : les textes de ce service ne permettent pas de répondre.", weak: "Pas de réponse : rien de suffisamment proche n'a été trouvé dans les textes.",
    scope: "Ce service ne contient que le Code du travail et le RGPD (pas les conventions collectives, pas la jurisprudence).",
    next: "Pour un cas précis, consultez un avocat, l'inspection du travail ou Légifrance.", why: "Raison donnée par le service :",
    found_weak: "Les {n} articles les plus proches (peu pertinents ici)", answer: "Réponse", where: "Où dans la loi ?",
    stored: "réponse déjà préparée", ai_note: "Cette réponse est rédigée par une intelligence artificielle à partir des articles ci-dessous ; elle peut comporter des erreurs, vérifiez les articles cités.", cited: "Passages cités", found: "Les {n} articles les plus proches de votre question",
    found_hint: "La réponse est écrite à partir de ces articles seulement, du plus proche au moins proche.",
    read: "Lire l'article", on: "sur", useful: "Cette réponse est-elle utile ?", thanks: "Merci, votre avis est enregistré.",
    kind: "Qu'est-ce qui ne va pas ? (facultatif)", wrong_answer: "La réponse est fausse", wrong_citation: "Une citation ne correspond pas",
    missing_article: "Un article manque", other: "Autre", comment: "Un commentaire ? (facultatif, 500 caractères au plus)", send: "Envoyer",
    vote_failed: "Le vote n'a pas pu être enregistré.", vote_limited: "Trop de votes d'affilée, réessayez dans un instant.",
    up: "Réponse utile", down: "Réponse pas utile", src_ct: "Code du travail", src_gdpr: "RGPD", src_none: "Hors des textes",
    masked_intro: "Pour protéger vos données, nous avons masqué dans votre question : {what}. Votre question avec la partie masquée : « {question} ». Les noms et les adresses postales ne sont pas détectés : évitez de les écrire.",
    pii_email: "une adresse e-mail", pii_phone: "un numéro de téléphone", pii_iban: "un IBAN", pii_card: "un numéro de carte bancaire",
    pii_nir: "un numéro de sécurité sociale", pii_birth: "une date de naissance",
  },
  en: {
    history_empty: "No questions yet.", history_show: "Show the answer", history_hide: "Hide the answer",
    history_show_result: "Show the result", history_hide_result: "Hide the result", history_answered: "Answered", history_noanswer: "No answer",
    history_edit: "Edit this question", history_delete: "Delete this entry",
    history_empty_tab: "This tab's list is lost when you close the tab: tick the box above to keep it on this device.",
    history_blocked: "Your browser does not allow keeping the history: the list will stay empty.",
    history_full: "The browser refuses to write (storage full or blocked): new questions will not be kept.",
    history_full_hint: "Delete entries to make room.",
    history_unreadable: "This entry cannot be read. You can delete it.",
    history_dated: "Answer given on {date}: the law may have changed since.", history_dated_result: "Result given on {date}: the law may have changed since.",
    busy: "Another question is already in progress from your connection: wait for its answer.",
    failed: "The service had a problem. Try again in a moment.",
    loaded: "Question taken from your history: change it if you wish, then send it.",
    translate_gone: "The service no longer holds this answer (7 days): it can no longer be translated.",
    not_saved: "This answer could not be kept in the history: the browser refuses or is full.",
    searching: "Searching…", translating: "Translating the question, then searching…", translated: "Question translated into French:", edit_question: "Edit the French", ask_again: "Ask again",
    show_english: "English translation of this answer", translating_answer: "Translating…",
    english_label: "Machine translation into English (the French text is authoritative)", translate_failed: "The translation could not be made.", empty: "Write a question.", network: "The service is not responding. Try again in a moment.",
    invalid: "The question must be 1 to 500 characters long.", limited: "Too many requests from you. Try again in {n}.",
    unavailable: "The service is temporarily unavailable", upstream: "The AI model did not answer. The articles found are shown below.",
    upstream_none: "The AI model did not answer. Try again in a moment.",
    translate_question_failed: "The translation of your question failed. Try again, or write it in French.",
    translate_unknown: "The service did not keep this answer: it cannot be translated.",
    pii_other: "personal data",
    noanswer: "No answer: the texts of this service do not allow one.", weak: "No answer: nothing close enough was found in the texts.",
    scope: "This service contains only the French labour code and the GDPR (no collective agreements, no case law).",
    next: "For a specific case, consult a lawyer, the labour inspectorate or Légifrance.", why: "Reason given by the service (in French):",
    found_weak: "The {n} closest articles (not very relevant here; in French)", answer: "Answer (in French)", where: "Where in the law? (in French)",
    stored: "ready-made answer", ai_note: "This answer is written by an artificial intelligence from the articles below; it may contain errors, check the cited articles.", cited: "Cited passages (in French)", found: "The {n} articles closest to your question (in French)",
    found_hint: "The answer is written from these articles only, from the closest to the least close.",
    read: "Read the article", on: "on", useful: "Was this answer useful?", thanks: "Thank you, your opinion is saved.",
    kind: "What is wrong? (optional)", wrong_answer: "The answer is wrong", wrong_citation: "A citation does not match",
    missing_article: "An article is missing", other: "Other", comment: "A comment? (optional, 500 characters at most)", send: "Send",
    vote_failed: "The vote could not be saved.", vote_limited: "Too many votes in a row, try again in a moment.",
    up: "Useful answer", down: "Answer not useful", src_ct: "Labour code", src_gdpr: "GDPR", src_none: "Outside the texts",
    masked_intro: "To protect your data, we masked in your question: {what}. Your question with the masked part: “{question}”. Names and postal addresses are not detected: avoid writing them.",
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
let asking = null; // "searching" or "translating" while a question is being answered

// "12 s" in French, "12 seconds" or "1 second" in English.
const waitText = (seconds) => (lang === "fr" ? `${seconds} s` : `${seconds} ${seconds === 1 ? "second" : "seconds"}`);

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

  let sending = false; // a second click while the first vote is on its way would send it twice
  async function submit(extra) {
    if (sending) return;
    sending = true;
    let status = 0;
    try { status = await sendVote(requestId, value, extra && kind.value, extra && comment.value.trim()); } catch (e) { /* offline: the message tells */ }
    sending = false;
    message.textContent = status === 200 ? t("thanks") : status === 429 ? t("vote_limited") : t("vote_failed");
  }
  function vote(chosen, button, other) {
    if (sending) return; // the first choice is on its way: the screen must show what was sent
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

// The claims of an answer in the shape the page draws: a text and a list of citations, each with a label, a passage, units, a place and a link.
function validClaims(claims) {
  return Array.isArray(claims) && claims.length > 0 && claims.every((claim) => claim && typeof claim.text === "string" && Array.isArray(claim.citations)
    && claim.citations.every((c) => c && typeof c.label === "string" && typeof c.passage === "string" && Array.isArray(c.units)
      && typeof c.section_path === "string" && typeof c.url === "string"));
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
  const aiNote = make("p", { class: "count", text: t("ai_note") }); // AI Act art. 50(1): say that an AI wrote it (docs/decisions/0010)
  if (history) return make("div", { class: "answer" }, label, aiNote, claims, englishBlock(reply), sources); // no vote, no list of articles
  return make("div", { class: "answer" }, label, aiNote, claims, englishBlock(reply), sources, foundArticles(reply.articles) || "", voteBox(reply.request_id));
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

// The labels the service writes in place of a masked identifier are French (answering/pii.py); the English page names them in English.
const PLACEHOLDERS_EN = { "[date de naissance]": "[date of birth]", "[numéro de sécurité sociale]": "[social security number]",
  "[carte bancaire]": "[bank card]", "[téléphone]": "[telephone]" };

function placeholdersIn(text) {
  if (lang !== "en" || typeof text !== "string") return text;
  return Object.entries(PLACEHOLDERS_EN).reduce((result, [french, english]) => result.split(french).join(english), text);
}

// Tells the visitor what the personal-data filter masked in the question, and the question that was really used.
function maskedNotice(reply) {
  if (!reply || !Array.isArray(reply.masked) || !reply.masked.length) return null;
  const what = [...new Set([...new Set(reply.masked)].map((kind) => (`pii_${kind}` in T[lang] ? t(`pii_${kind}`) : t("pii_other"))))].join(", ");
  return make("p", { class: "notice", text: t("masked_intro", { what, question: placeholdersIn(reply.question_masked) }) });
}

function show() {
  const result = document.getElementById("result");
  if (!result) return;
  result.replaceChildren();
  if (asking) { result.append(make("div", { class: "status", text: t(asking) })); return; } // a request is running: not an old answer
  if (!last) return;
  drawReply();
  // the French line stays after a failed "ask again" from it, so that the visitor need not translate again
  const french = last.reply && last.reply.question_fr ? last.reply : (last.frenchLine ? { question_fr: last.frenchLine } : null);
  const line = translatedLine(french);
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
const ANSWER_KEPT_MS = 7 * 24 * 3600 * 1000; // the service keeps an answer 7 days (TTL of answering/cache.py)

function englishBlock(reply) {
  if (reply.outcome !== "answered" || !(reply.question_fr || lang === "en")) return "";
  if (reply.english) return savedEnglish(reply); // already asked for: shown again after a change of language, never requested twice
  const box = make("div", { class: "en-answer" });
  if (reply.english_gone || (reply.at && Date.now() - Date.parse(reply.at) > ANSWER_KEPT_MS)) { // the service no longer holds the answer
    box.append(make("span", { class: "count", text: t("translate_gone") }));
    return box;
  }
  const button = make("button", { type: "button", class: "pill", text: t("show_english") });
  if (translating.has(reply.request_id)) button.disabled = true; // the page was drawn again while the request runs
  button.addEventListener("click", () => askEnglish(reply, box, button));
  box.append(button);
  boxes.set(reply.request_id, { box, button });
  return box;
}

// One request for the translation of an answer. The note of an earlier try is reused, so that notes do not pile up.
const translating = new Set(); // the requests whose answer is being translated: one request each, whatever is drawn again meanwhile
const boxes = new Map(); // request id -> the translation box and button on screen now (the latest drawn)

async function askEnglish(reply, box, button) {
  if (translating.has(reply.request_id)) return;
  translating.add(reply.request_id);
  try { await askEnglishOnce(reply, box, button); } finally { translating.delete(reply.request_id); }
}

function showNote(target, text) {
  if (!target.button.note) {
    target.button.note = make("span", { class: "count" });
    target.box.append(target.button.note);
  }
  target.button.note.textContent = ` ${text}`;
}

async function askEnglishOnce(reply, box, button) {
  button.disabled = true;
  showNote({ box, button }, t("translating_answer"));
  let message = t("translate_failed");
  try {
    const response = await fetch("/translate-answer", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_id: reply.request_id }) });
    const data = await response.json().catch(() => ({}));
    if (response.status === 200 && typeof data.english === "string" && data.english.trim()) {
      box.replaceChildren(make("span", { class: "tr-label", text: t("english_label") }), withMarkers(data.english));
      reply.english = data.english;
      refreshHistory(updateEntry(reply.request_id, { english: data.english }));
      showLate(reply, box);
      return;
    }
    if (response.status === 429) message = t("limited", { n: waitText(Number(response.headers.get("Retry-After")) || 60) });
    if (response.status === 404) message = t("translate_unknown"); // the service never had this answer: not remembered, a proxy fault could look the same
    if (response.status === 410) { // the service keeps an answer 7 days; the button stays off, also after a redraw
      reply.english_gone = true;
      refreshHistory(updateEntry(reply.request_id, { english_gone: true }));
      const here = boxes.get(reply.request_id) || { box, button }; // the box on screen may be a newer one than the one that asked
      showNote(here, t("translate_gone"));
      showLate(reply, box);
      return;
    }
  } catch (e) { /* the message below tells */ }
  const here = boxes.get(reply.request_id) || { box, button };
  here.button.disabled = false;
  showNote(here, message);
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
  if (status === 429) return problemCard(t("limited", { n: waitText(retryAfter || (reply && reply.retry_after) || 60) }), reply, history);
  if (status === 503) return problemCard(`${t("unavailable")}.`, reply, history);
  if (status === 502) return problemCard(t(reply && Array.isArray(reply.articles) && reply.articles.length ? "upstream" : "upstream_none"), reply, history);
  if (status !== 200 || !reply || typeof reply !== "object") return problemCard(t("failed"), null, history); // 500, 504, 404...: never a refusal
  if (reply.outcome === "answered") {
    return validClaims(reply.claims) ? answerCard(reply, history) : problemCard(t("failed"), null, history);
  }
  if (reply.outcome === "refused_weak_retrieval") return refusalCard(t("weak"), { ...reply, reason: null }, history);
  if (REFUSALS.includes(reply.outcome)) return refusalCard(t("noanswer"), reply, history);
  return problemCard(t("failed"), null, history); // an outcome this page does not know
}

const REFUSALS = ["refused_by_model", "invalid_citation"]; // the other outcome with no answer, refused_weak_retrieval, has its own wording

function drawReply() {
  const { reply, status, retryAfter } = last;
  let node;
  try {
    // a failed translation of the question is a 502 too, but it has no articles and nothing to vote on
    const noArticles = !(reply && Array.isArray(reply.articles) && reply.articles.length);
    node = status === 502 && last.translating && noArticles ? problemCard(t("translate_question_failed"), null) : replyNode(reply, status, retryAfter);
  } catch (e) { node = problemCard(t("failed"), null); } // a reply of the wrong shape
  document.getElementById("result").append(node);
}

// The answer area is just under the question box; bring it into view, since the visitor may have clicked a card far below.
function showResultArea() {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.getElementById("result").scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
}

// `fromField`: the question is the French text of the translated-question field (kept on screen, since it is what was searched).
async function ask(question, translate = false, fromField = false) {
  if (asking) return; // one question at a time on this page: a second one would only be refused by the service
  asking = translate ? "translating" : "searching";
  const go = document.getElementById("go");
  const translateButton = document.getElementById("translate");
  const result = document.getElementById("result");
  // Asked again from the French line: the entry keeps the English the visitor wrote, and replaces the one of the first try.
  const previous = last && last.reply ? last.reply.request_id : null;
  const typed = fromField && last && last.original ? last.original : question;
  try {
    result.replaceChildren(make("div", { class: "status", text: t(asking) }));
    showResultArea();
    go.disabled = true;
    if (translateButton) translateButton.disabled = true;
    const response = await fetch("/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, translate }) });
    let reply = null;
    try { reply = await response.json(); } catch (e) { /* not JSON: the status tells */ }
    if (reply !== null && typeof reply !== "object") reply = null; // a text or a number is no reply
    if (fromField && reply && response.status !== 422) reply.question_fr = question;
    last = { reply: response.status === 422 ? null : reply, status: response.status, retryAfter: Number(response.headers.get("Retry-After")) || null,
      original: typed, translating: translate, frenchLine: fromField ? question : null };
    if (response.status === 200 && reply) last.notSaved = addToHistory(typed, reply, fromField ? previous : null) === false;
  } catch (e) {
    last = { reply: null, status: 0, original: typed, translating: translate, frenchLine: fromField ? question : null };
  } finally {
    asking = null;
    go.disabled = false;
    if (translateButton) translateButton.disabled = false;
  }
  show();
  showResultArea();
  result.setAttribute("tabindex", "-1"); // the redrawn area takes the keyboard focus, which was on a button that no longer exists
  result.focus({ preventScroll: true });
}

function drawExamples() {
  const cards = document.getElementById("cards");
  if (!cards) return;
  cards.replaceChildren(...examples.map((e) => {
    const card = make("button", { type: "button", class: "card" }, tag(e.source), make("b", { text: e.label[lang] || e.label.fr }),
      make("span", { text: e.question }), lang === "en" && e.question_en ? make("span", { class: "gloss", text: `(${e.question_en})` }) : "");
    card.addEventListener("click", () => {
      if (asking) return; // the box and the answer shown must belong to the same question
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

function setup() {
  applyLanguage();
  window.addEventListener("blur", noteFocusLoss);
  document.addEventListener("visibilitychange", noteFocusLoss);
  for (const link of document.querySelectorAll("a.mail")) {
    for (const type of ["mouseenter", "focus", "touchstart"]) link.addEventListener(type, prepareMail);
    link.addEventListener("click", openMail);
  }
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
    if (asking) return; // the busy line stays
    const question = box.value.trim();
    if (question) ask(question);
    else document.getElementById("result").replaceChildren(make("div", { class: "status problem", text: t("empty") }));
  });
  fetch("/examples").then((r) => r.json()).then((list) => { examples = list; drawExamples(); }).catch(() => { /* no examples: the box still works */ });
}

setup();
