// The contact link (step 0f, part 4): the mail address is built when the link is used. Loaded before app.js, which
// sets it up.
"use strict";

// The contact address is never written in the page: it is put together when the visitor clicks, so that programs
// which read pages for addresses do not find it.
// A browser cannot say whether a mailto worked; when a mail program opens, the page loses focus. No loss of focus
// within MAIL_WAIT_MS: the address is shown as text instead.
const MAIL_WAIT_MS = 1500;
let lastFocusLoss = 0;

function noteFocusLoss() { lastFocusLoss = Date.now(); }

function showAddress(link, address, startedAt) {
  if (lastFocusLoss >= startedAt || link.addressNote) return;
  link.addressNote = document.createElement("span");
  link.addressNote.textContent = ` (${address})`;
  link.after(link.addressNote);
}

// The real mailto target is set when the visitor reaches the link (hover, tab) or clicks it, and the browser then
// follows it as an ordinary link, which works in more browsers than a script navigation.
function prepareMail(event) {
  const link = event.currentTarget;
  link.setAttribute("href", `mailto:${link.dataset.user}@${link.dataset.host}`);
}

function openMail(event) {
  const link = event.currentTarget;
  prepareMail(event);
  setTimeout(showAddress, MAIL_WAIT_MS, link, `${link.dataset.user}@${link.dataset.host}`, Date.now());
}
