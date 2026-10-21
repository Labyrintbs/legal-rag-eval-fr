# Global Preferences

## Code comments
Keep comments concise and only add them when necessary (non-obvious logic, tricky workarounds, important caveats). Do not comment on things that are already clear from the code itself.

- Max 1-3 lines: state the constraint plus one piece of evidence, not the full investigation narrative. Longer justifications belong in the commit message.
- One authority per fact: point back to the original ("see X") instead of re-typing the same reasoning in another file. This applies while drafting too — when one change adds comments across several files (e.g. a config file and the code that reads it), pick one of them as the authority before writing any of them, then make the rest short pointers. Check this before finishing the change, not only when later editing a comment that already exists.
- Don't freeze a live measurement (a count, a rate) into a comment as permanent fact — drop the number, or label it a snapshot ("as of [date]").
- Reserve "verified live"/"confirmed" for genuinely surprising facts, not as a routine rigor badge.
- A loop/branch with a non-obvious aggregation or selection rule (e.g. keeping a running best/max instead of summing, an intentional early-exit, a tiebreak) gets a short comment stating the intent, unprompted — the code already shows what happens each iteration, not why that accumulation pattern was chosen over the more obvious one.

## Commit messages
- Do not include "Claude" or "Claude Code" (or any co-author/generated-by attribution referencing Claude) in commit messages.
- Keep commit messages simple and concise.

## Tests
When a change directly affects the existing workflow (pipeline logic, scoring/filtering, prompts, DB queries, data flow), read the repo's existing tests first, then add test cases for it in the same style and run the full suite before finishing. Simple changes (comment edits, added log/verbose output) need no tests.

## Delete commands
Before running any delete/destructive command (e.g. `rm`, `git clean`, dropping data, deleting files/branches), show the before and after state of the operation, and wait for explicit confirmation before executing.

## Explaining unfamiliar things
When asked to explain something the user hasn't encountered before, lead with plain words and a small, concrete, easy-to-follow example before reaching for jargon or technical terminology. Introduce the term itself only after the underlying idea has already landed through the example.

When explaining how a function/module works, always give the plain-language explanation of its overall logic and purpose FIRST, with no code shown at all — then follow with code-level details (line-by-line walkthrough, syntax) as a separate, later section. Never interleave code into the initial plain explanation.

Keep explanations plain and highly condensed: short, direct statements, minimal words. Avoid scene-setting/narrative framing ("picture this," "let's trace," multi-paragraph windups) and avoid padding a point with extra restatements — say each thing once, plainly, and stop.

If an explanation touches a term/detail not already established in the conversation, define it plainly on the spot before using it — don't assume it's understood just because it appeared in code or a prior message.

Never invent a new synonym/label for a concept that already has an established name (from the codebase or earlier in the conversation) — e.g. don't say "deep-checked" when the codebase/conversation already calls it "enrichment." Use the existing term.

Use common, everyday words, not informal shorthand or invented compound terms (e.g. not "re-sighting," "bump," "hit-counter") — say "seeing it again," "increase," "counter that tracks how many times it matched."
