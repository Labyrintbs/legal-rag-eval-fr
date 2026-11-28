# Privacy text and legal items (phase 4 of the deployment plan; draft for review, 2026-11-28)

Nothing here is applied to `privacy.html`, `texts_en.js` or the answer card until the owner approves the text. Source marks: **(read)** a primary page or PDF read in full for this point; **(summary)** from a page summary; **(unverified)** from memory.

## 1. What is false on the page today

| Sentence of the page | Why it is wrong now | Fix |
|---|---|---|
| "votre question est envoyée à un fournisseur de modèle d'IA (DeepSeek). Ses serveurs peuvent se trouver hors de l'Union européenne" | The model runs at Scaleway (France, Paris); DeepSeek the company does not receive the question | section 3.1 |
| "hébergé chez un prestataire technique, qui voit les connexions" | The host is not named; LCEN art. 1-1 II asks for its name and address | section 3.2 |
| The retention table has no line for the host's disk copy | OVH copies the whole server disk every day (one restore point, replaced daily); it holds the traces still present | section 3.3 |
| The page nowhere says the answer is written by an AI | AI Act art. 50(1): people must be told they interact with an AI system unless it is obvious | section 3.4 |
| The page nowhere says the model is a preview version | Scaleway: a preview model may change or go with one month of notice | section 3.1 |

## 2. What I need from the owner before the text is final

1. **The country of the VPS's data centre**, from the control panel (the VPS overview). The host is **not** named (owner's decision, 2026-11-28; see 3.2).
2. **Decided:** the author's name and the contact link stay on the page: GDPR art. 13 asks for the controller's identity and contact details **(read)**, so the anonymity route of LCEN art. 1-1 II does not fit a service that processes visitors' questions.
3. **Approve or edit the French text below** (the English text follows it word for word in meaning).

## 3. Proposed text (changed or new blocks only)

### 3.1 "Qui reçoit votre question" (replaces `pv_recv`; `pv_filter` stays as it is)

FR: *Pour écrire la réponse, votre question est envoyée à Scaleway, une société française, qui fait fonctionner un modèle d'IA (DeepSeek V4.1 Flash) sur ses propres serveurs, actuellement à Paris. Votre question n'est donc pas envoyée à DeepSeek, et Scaleway ne reçoit ni votre adresse réseau ni rien d'autre que le texte de la question. Selon son contrat, Scaleway ne conserve ni la question ni la réponse après le traitement et ne s'en sert pas pour entraîner un modèle ; une seule exception : en cas d'activité anormale ou malveillante, le contenu d'une requête peut être conservé temporairement. Scaleway peut ajouter d'autres lieux en Europe, en prévenant ses clients. Le modèle est une version préliminaire (« preview ») : il peut être modifié ou retiré avec un mois de préavis, et aucun niveau de service n'est garanti. N'écrivez aucune information personnelle.*

EN: *To write the answer, your question is sent to Scaleway, a French company, which runs an AI model (DeepSeek V4.1 Flash) on its own servers, currently in Paris. So your question is not sent to DeepSeek, and Scaleway receives neither your network address nor anything else than the text of the question. According to its contract, Scaleway keeps neither the question nor the answer after processing and does not use them to train a model; one exception: in case of abnormal or malicious activity, the content of a request may be kept temporarily. Scaleway may add other places in Europe, and says it will tell its customers. The model is a preview version: it may be changed or withdrawn with one month of notice, and no service level is guaranteed. Do not write any personal information.*

Sources: Specific Conditions of 2026-09-21, art. 2.4, and the Generative APIs FAQ and lifecycle pages **(read, in `0009`, D2)**. The first sentence's "Scaleway receives nothing else than the text of the question" is true of the code: the request holds the prompt, the five articles and the question; it must stay true (a test would be added with the change).

### 3.2 New section "Hébergement" (decision of the owner, 2026-11-28: the host is not named)

FR: *Éditeur : Hongming Fang, personne physique, à titre non professionnel et sans but lucratif. Le service est hébergé chez un prestataire technique, dont les serveurs sont situés en [pays : à compléter]. Il voit les connexions (adresses réseau) ; il ne reçoit pas le contenu des questions en clair si le site est servi en HTTPS.*
EN: *Publisher: Hongming Fang, a private person, non-professionally and without profit. The service is hosted by a technical provider whose servers are located in [country: to fill in]. It sees the connections (network addresses); it does not receive the content of the questions in clear if the site is served over HTTPS.*

Why the host is not named: LCEN art. 1-1 **(read)** asks a professional editor to show its own identity and the host's; a non-professional editor *may* show only the host's name and address to stay anonymous (art. 1-1 II). A named, non-professional, non-commercial editor (this case) is not clearly required to show the host as well; this is the author's reading and **not legal advice (unverified)**. The risk: a portfolio used to look for work could be read as professional, and the rule would then apply (art. 1-2: one year in prison and 75,000 euros); adding the host's name and address is a one-line change if that ever matters. GDPR art. 13 asks only for the "recipients or categories of recipients" **(read)**, so "a technical provider" is enough. The sentence on HTTPS is true only after HTTPS is on (phase 5). No separate "mentions légales" page is required **(read)**.

### 3.3 Two new rows in the retention table

| Data | Duration |
|---|---|
| FR: *Copie du disque du serveur faite chaque jour par l'hébergeur : elle contient ce que le service garde à ce moment-là* · EN: *Copy of the server's disk made each day by the host: it holds what the service keeps at that moment* | FR: *Remplacée chaque jour (au plus un jour de plus que les durées ci-dessus)* · EN: *Replaced each day (at most one day beyond the durations above)* |
| FR: *Sauvegarde chiffrée des articles de loi, des vecteurs et des réglages (aucune question, aucune réponse, aucune adresse)* · EN: *Encrypted backup of the legal articles, the vectors and the settings (no question, no answer, no address)* | FR: *Une copie par jour pendant 7 jours, puis une par semaine pendant 4 semaines* · EN: *One copy a day for 7 days, then one a week for 4 weeks* |

### 3.4 AI notice (page and answer card)

FR (a line under every written answer, and the sentence in "Comment ça marche" stays): *Cette réponse est rédigée par une intelligence artificielle à partir des articles ci-dessous ; elle peut comporter des erreurs, vérifiez les articles cités.*
EN: *This answer is written by an artificial intelligence from the articles below; it may contain errors, check the cited articles.*

Why: AI Act art. 50(1) **(read, from a site that reproduces the Official Journal; EUR-Lex itself returned an empty page)**: providers of "AI systems intended to interact directly with natural persons" must see that "the persons concerned are informed that they are interacting with an AI system", unless it is obvious to a reasonably well-informed person; art. 50 applies from 2 August 2026, and the Commission page (updated 2026-11-27) lists the AI Omnibus changes without any postponement of art. 50 **(read; the Omnibus text itself was not read)**. Whether this demo is a "provider" in the sense of the Act is not decided by the pages read; the line costs nothing, so it is added either way. Art. 50(4) (disclosing AI-generated text published to inform the public on matters of public interest) falls on deployers and has an exception for human review; whether answers to individual questions are "published" is not clear: **unverified, the same line covers it.**

## 4. Record of processing (GDPR art. 30), half a page

The exemption in art. 30(5) does not apply to processing that is "not occasional" **(read)**; the CNIL says in practice it is "limitée à des cas très particuliers" and advises to keep the record in case of doubt **(read)**. This service runs continuously, so it keeps one. The CNIL form is only "sous une forme écrite" **(read)**; the CNIL template (ODS) was not opened.

| Field | Entry |
|---|---|
| Controller | Hongming Fang (private person), contact: the address on the page |
| Purpose | answering visitors' legal questions; limiting abuse and cost; improving the tests of the service (after removal of personal data by a person) |
| Legal basis | legitimate interest of the author (art. 6(1)(f)) |
| People | visitors of the service |
| Data | question, answer, optional vote and comment, date, result of the search; a daily-changing hash of the network address; cached answer (without the question) |
| Recipients (processors) | Scaleway SAS (model; contract and DPA of 2024-06-01 read); OVHcloud (hosting, copy of the disk); Healthchecks.io receives pings with no visitor data and is therefore not a recipient of personal data |
| Transfers | none outside the EU intended: Scaleway's DPA says services are in the EU by default and requires prior information and the Standard Contractual Clauses for any other place; no sub-processor outside the EU is on Scaleway's list **(read)**; the host's data centre: to confirm |
| Retention | the table of the page: 7 days for ordinary text, 30 for failures, voted or commented requests and one request in 20; cache 7 days at most; the disk copy of the host replaced daily |
| Security | no account, no cookie; the address is stored only as a hash with a secret and the day; masking filter for identifiers; request size and rate limits; only the web proxy is published by the stack, and while the site is private only SSH answers from outside (tested 2026-11-27); secrets in a file readable by its owner only; backups encrypted before upload and without visitor data; separate keys for the model and the backup; hourly erase job with a heartbeat; kill switch |

## 5. Data protection impact assessment (DPIA): proposed decision

- GDPR art. 35(3) **(read)** names three cases (systematic and extensive evaluation with significant effects, large-scale sensitive data, large-scale monitoring of a public area); none fits.
- The CNIL list of processing types needing a DPIA **(read, from the PDF of the 2018 deliberation, 14 types)**: health institutions' files, genetic data, HR profiling, constant staff monitoring, whistle-blowing systems, health data warehouses, profiling that can end a contract, shared lists of contract defaults, profiling from external data, biometrics for vulnerable people, social-housing files, social support, large-scale location data. **None resembles a public question-and-answer service.** The list says it is not exhaustive and refers to nine criteria **(read)**; the criteria seen in the list are scoring, automated decisions with legal effect, systematic monitoring, sensitive data, large scale, combining datasets, vulnerable people and innovative use of technology. This service meets at most **one** of them (innovative use: a language model); sensitive data may appear by accident in free text, which is why the page says not to write personal data, the filter masks identifiers and text is erased after 7 days. The "two criteria or more" rule of the EDPB guidelines is **unverified** (not read).
- Proposed decision: **no DPIA, with this reasoning written down**; reconsider if the service reaches a large audience, adds accounts, profiling or a purpose with sensitive data, or if a model is used for decisions about people. Option: do a light DPIA anyway with the CNIL tool; not recommended for a demo of this size.

## 6. Breach procedure (GDPR art. 33)

- **Duty (read):** notify the CNIL within 72 hours of becoming aware of a breach, unless it is unlikely to result in a risk; notify the people only if the risk is high (art. 34); in every case write the facts, effects and remedy in an internal register. Notice is online at the CNIL's notification service for controllers; a first notice may be followed by a complement.
- **Steps for this service:** (1) contain: `legalrag service llm-off`, stop the proxy (`docker compose stop proxy`), revoke the IAM keys and the SSH key concerned; (2) keep evidence (logs: `journalctl`, the app log; do not rebuild before copying them); (3) assess: which data (traces hold text for 7 or 30 days; hashes of addresses change daily and cannot be traced back without the secret), how many people, what risk; (4) notify the CNIL within 72 hours if there is a risk; (5) tell Scaleway or OVH if their service is involved; (6) write the entry; (7) fix and test, then note the lesson in `OPERATIONS.md`.
- **Register:** one line per incident (date found, what, data, number of people, risk, notified or not and why, remedy), kept by the owner outside the repository (it may hold personal facts).

## 7. Open points and what is unverified

- The country of the VPS's data centre (section 2). OVH's legal details were not read; they are not needed while the host is not named.
- AI Act: the Official Journal text and art. 113 were not read; the Omnibus text was not read; provider or deployer status undecided.
- DPIA: the 2018 list was read; a later update was not checked; the EDPB threshold is unverified.
- CNIL information page of 2019 and the record page of 2018: current wording not re-checked.
- Not yet checked: the "no cookie" claim against CNIL guidance (D9), and whether the browser history feature needs a mention (it is stored in the visitor's own browser).
