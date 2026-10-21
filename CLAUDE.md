# Project rules for Claude sessions

French legal RAG (Code du travail + GDPR) with measured evaluation. The repo is public: no secrets, raw data, personal information or embeddings in git.

To continue Loop 3 on the Windows laptop, read `docs/handoff/loop3_windows_embedding.md` first. Every data-processing or chunking change is logged with its measured effect in `EXPERIMENT.md`.

## How to work with the user
- Evidence, not defaults: search for real sources or measure on real data before proposing. Cite sources. Mark claims that come from memory as unverified.
- For any design choice give 2 to 4 options with trade-offs and a recommendation. One decision at a time, in dependency order. Expect each assumption to be challenged.
- Explain plainly first, with a small concrete example, before any jargon. Define a term before using it. Use the name a concept already has in the code or the conversation; do not invent synonyms. Short, direct sentences, no padding.
- Each loop and stage ends with a review gate; do not start the next one before the user approves.
- Report honestly: what was verified, what was not, and any test failure with its output.
- Ask before anything that spends money, deletes or overwrites, or is outward-facing. Before any delete or destructive command, show the before and after state and wait for confirmation.

## Code and git
- The user's global coding rules (comments, commit messages, tests, delete commands, how to explain) are in `docs/handoff/global_CLAUDE.md`. If they are not installed on this machine (`~/.claude/CLAUDE.md`), follow that file anyway.
- Push to origin after every commit.
- Make code changes with the editor tools (a reviewable diff), not shell one-liners.
- Run the full suite with `uv run pytest` and lint with `uv run ruff check .` before finishing.
