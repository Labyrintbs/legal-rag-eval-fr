# Personal website: context for a new session (written 2026-11-28)

For an agent or session that builds the owner's personal website in **another repository**. Read this first, then `CLAUDE.md` of that repository. This file lives in a public repository: no secrets, no server address, no contact details belong in it.

## Who and why
- The owner is Hongming Fang (name already public on the demo's pages and on LinkedIn). They are learning system design alongside the code and are looking for work: the site shows what they built, **for HR readers and other non-specialists**, with pictures, short summaries and measured results, next to links to live demos and GitHub.
- The first project to show is `legal-rag-eval-fr` (this repository): a French legal question-answering demo (Code du travail and GDPR) with measured evaluation. It is not on the web yet; its public address is part of phase 5 of `docs/decisions/0009-deployment-stage-plan.md` (section 5b).

## Decisions made with the owner (2026-11-28)
1. **One personal domain.** The personal site is on the main name; **each project gets a subdomain** of it. This project will be `droit.<domain>` (label to confirm). A subdomain costs nothing extra: it is one more DNS record.
2. Ending **.fr** at OVH (OVH public catalogue, first year about 5 euros then about 8, excluding VAT); the registrar choice and the exact spelling are being settled in the demo's phase 5 (`0009`, D11 has the research).
3. **Separate repository and separate hosting** for the personal site, so the portfolio stays up when the demo server is rebuilt. Recommended host: **GitHub Pages** (free, custom domain, HTTPS); a static site generator (Astro or Eleventy: Markdown in, HTML out) rather than a framework app or a site builder. These recommendations are the previous session's, **not yet confirmed by the owner**.
4. French **and** English versions are recommended (not yet confirmed). Plain words, no jargon first: the readers are HR people.
5. No cookies, no analytics, no trackers (keeps the privacy note short and needs no banner). Decide with the owner before adding any counter.

## How the DNS will look
```
<domain>              A / AAAA -> the personal site's host (GitHub Pages IPs, or its CNAME target)
www.<domain>          CNAME    -> <domain>
droit.<domain>        A / AAAA -> the demo's VPS (set up in the demo repository's phase 5)
<domain>              TXT      -> v=spf1 -all   (the domain sends no mail)
```
DNS is hosted at the registrar. Short TTL (300 s) while setting up, raised later. DNSSEC on. Only the demo repository's session touches the `droit.` records and the VPS.

## What the demo provides for the site (all measured; dev questions only, the test half is still closed)
- Quality on 65 dev questions with the model used by the service: 85.6% of the answer's claims supported by the cited articles (a judge model; same family as the answering model), 54 of 58 answerable questions answered, a gold article cited in 52 of those 54; no real difference from the first provider tried (DeepSeek's own API: 85.0%). Source: `0009`, D2, "comparison results".
- Cost and speed: about 0.2 US cents counted per answer (no cache), model time median 1.5 s, whole answer 1 to 3 s; a simulated load of 20 visitors served 97% of requests with median 1.5 s. Source: `0009`, D2 and 5b; `OPERATIONS.md`.
- Design points a reader can understand: every sentence of an answer must cite the exact passage; an answer without a valid citation is refused; retention table on the privacy page; backups without visitor data; failures shown honestly. Source: `README.md`, `docs/CODE_MAP.md`, the method page of the demo.
- Screenshots: the demo runs privately on the owner's Mac (`legalrag serve`) and on the VPS through an SSH tunnel; once public, take them from the public address. Pictures must not show real visitors' questions or any address or key.
- Links: the GitHub repository `Labyrintbs/legal-rag-eval-fr` and the live demo address (to be filled in when public).

## Content plan (a starting point to review with the owner)
- Home: one line (who they are, what they build), the project cards, a contact link.
- Each project, in this order: the problem and who it is for in one line; what was built in two or three sentences with a picture; **results with numbers**; links (demo, code, write-up); the owner's role and the tools.
- About (short), a downloadable CV (the owner provides it), contact: build the mail link on click, as the demo does (`src/legalrag/web/static/mail.js`), so the address is not in the page source.
- Accessibility and speed: readable on a phone, text alternatives for pictures, no heavy scripts.

## Privacy and legal for the personal site
- Its own short privacy and contact note, drafted the same way as the demo's (`docs/decisions/0010-privacy-and-legal-text.md` shows the method and the sources read). With no cookies and no analytics there is little to say; say what the host (for example GitHub Pages) may log, after reading its current statement (not done).
- French site notices: LCEN art. 1-1 (read on Légifrance on 2026-11-28): a non-professional editor who names themselves is not clearly required to show the host; a portfolio used to look for work could be read as professional, in which case the owner's identity and the host's name and address would be needed. The owner decided not to show the host on the demo; decide again for this site (our reading, not legal advice).
- Do not use protected titles in names (avocat, notaire, huissier, conseil juridique): Code pénal art. 433-17.

## How the owner likes to work (also in `CLAUDE.md`)
- Explain plainly first, with a small concrete example, before any jargon; name the common alternatives of a design choice and when each is preferred. Short, direct sentences.
- For any design choice give two to four options with trade-offs and a recommendation; one decision at a time, in dependency order; expect each assumption to be challenged.
- Each stage ends with a review gate: do not start the next before the owner approves. Ask before anything that spends money, deletes or overwrites, or is outward-facing; before a destructive command show the before and after state.
- Evidence, not defaults: read real sources, say what was verified and what was not, cite them.
- Code changes with the editor tools, tests added for behaviour changes, commit messages short and without any tool attribution, push after every commit.

## Open questions for the owner
1. ~~The exact spelling and the subdomain label~~ Chosen 2026-11-28: `hongmingfang.fr` and `droit.hongmingfang.fr` for the demo (registration at OVH in progress: check the demo's plan, D11, for the state).
2. Hosting and tooling of the site (GitHub Pages plus a static generator is recommended).
3. Languages (French only, or French and English).
4. Which projects to show first, and the CV file.
5. Whether the portfolio counts as professional for the French site notices.
