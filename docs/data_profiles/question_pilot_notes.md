# Question writer pilot (step 0b)

Run on 2026-10-27 with `scripts/pilot_questions.py`: 3 articles (L1237-1, L4121-3-1, GDPR article 17 in French) x 2 styles x 2 writers (`deepseek-flash`, `deepseek-v4-pro`), thinking off. `deepseek-v4-pro` reviews the flash questions plus 4 planted questions on L1237-1. Style v1 first, then v2 (adds a counter-example against compound questions, a 30-word limit, neutral short answers). Prompts: `prompts/`. Raw results and the ledger are in `data/` (not committed). This is 6 questions per writer and style: an inspection of the process, not a measure of quality.

## Cost

| Run | Calls | Estimated cost (ledger) | Worst case (dry run) |
|---|---|---|---|
| v1 | 22 | 0.0109 USD | 0.0587 USD |
| v2 | 22 | 0.0093 USD | 0.0600 USD |

- The estimate before a call is about 2x the billed prompt tokens (the character ratio is an upper bound), so the caps are stricter than needed.
- The account balance dropped by 0.07 CNY over both runs (46.67 to 46.60). The ledger estimate for both is 0.0202 USD. The balance has two decimals and updates with a delay, so this size cannot pin down the exchange rate or whether reasoning tokens are billed (they were off here). To reconcile on the 20-question batch.

## What the pilot showed

- **22 of 22 answers were valid JSON in both runs; none empty.** One v2 pro answer used the key `reponce_courte`; the automatic check flagged it.
- **Compound questions.** v1: 1 of 6 flash questions asked two things at once. v2: 0 of 6 (6 questions, so weak evidence). The automatic check now also flags "et combien", "et est-ce que" and similar, and questions above 30 words.
- **Reviewer on 4 planted defects, v1 and v2:** correctly rejected the answer not in the article and the invented fact, accepted the good question. For the planted question that copies the article wording in lay style, it accepted both times (v1 `copies_article_wording: false`, v2 `true` but still accepted). The automatic overlap check flagged it both times.
- **A doubtful case the reviewer caught (v2, flash, lay, L4121-3-1):** "Au bout de combien de temps peut-on encore demander à voir le document...?" with the answer "au moins quarante ans". The article gives a minimum conservation period, not a deadline for consulting it. Rejected.
- **Pro lay question on L4121-3-1** asks about a transitional date (1 July 2023, for companies of 150 or more); the article does say so. Not reviewed in the pilot. Pro tends to pick details like this.
- Flash costs about 3 to 5 times less per call than pro. The reviewer ran with thinking off.

## Decisions taken from it

Flash writes with `plain.v2` and `lay.v2`, pro reviews with thinking off, automatic checks run first on every question; revisit the reviewer's effort after the full set. See `docs/decisions/0003-step-0b-decisions.md`.
