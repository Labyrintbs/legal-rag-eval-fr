# Experiment log

Every change to data processing or chunking gets one entry, newest last. Each entry is committed together with the change it describes.

Entry template:

```
## YYYY-MM-DD: short title
- Change:
- Why:
- Measured effect (counts, token statistics, checks):
- Commit:
```

## 2026-10-20: starting values
- Change: initial settings, not yet implemented.
  - One article = one chunk. Split only above 1,024 bge-m3 tokens, no overlap.
  - Code du travail splits at sentence boundaries, GDPR at paragraph boundaries.
  - Heading line: code name + article number + last 3 levels of the section path.
- Why: planned from earlier measurements (see `docs/data_profiles/` once written).
- Measured effect: none yet.
- Commit: scaffold.

## 2026-10-20: Code du travail data profile (Loop 1, step 1)
- Change: added `legalrag.sources.legi` (filter + profile) and `docs/data_profiles/code_travail.md`. No chunking yet.
- Why: decide unit and heading from real data before building the chunker.
- Measured effect: all spec counts reproduced (11,433 rows, 133 extra duplicate bodies = 209 rows in 76 groups, token percentiles, 37 bodies over 1,024). Differences from the spec:
  - `R*3231-4`-style numbers (14 articles) are real decree articles, not annexes. Real annexes: 8. The kind rule must allow an optional `*`.
  - 4 `article_num` values have leading or trailing whitespace (for example ` L1251-33-1`). They must be stripped.
  - 17 section paths contain a carriage return (`\r`). Bodies contain no unusual characters.
- Commit: see git log.

## 2026-10-20: first chunker for Code du travail (Loop 1, steps 2-4)
- Change: added text normalisation (`text.py`), header builder (`chunking/header.py`), sentence splitter and packer (`chunking/split.py`), `ingest.build_chunks`, `verify.py`, CLI (`make profile`, `make verify`) and 18 tests on a fixture of 18 real articles (`scripts/make_fixture.py`).
  - Settings: header style `last_k` with k=3; one article = one chunk; split only above 1,024 bge-m3 tokens (header included); no overlap.
  - Sentence rule: split at `.`, `!` or `?` followed by whitespace and a capital letter or digit, except after a single capital letter (`L.`, `R.`, `D.`) or `art`, `al`, `n°`-style abbreviations.
  - Fallback: a piece longer than the budget is cut into word windows.
  - `section_path` is stored as in the source; carriage returns and other whitespace are cleaned only when the header is built.
- Why: spec section 6, with the data-profile findings above.
- Measured effect: 11,433 articles give 11,563 chunks (130 extra pieces). 46 articles are split (largest: 31 pieces). 36 chunks needed word windows (no sentence boundary, mostly flattened annex tables). No chunk over 1,024 tokens (max 1,022). All 10 `make verify` checks pass. 18 tests pass.
- Open: the Légifrance URL pattern returns 403 to scripts, so it must be checked by hand in a browser (see `docs/data_profiles/spot_check_code_travail.md`).
- Commit: see git log.

## 2026-10-20: spot check 1 of 20 and repeated levels in section paths
- Change: none in code. First manual check on legifrance.gouv.fr (L3132-25-3).
- Measured effect: the URL pattern works, the in-force date and the last levels of the path match the site. The data path has 10 levels, the site shows 9: an extra "Paragraphe 3 : Dérogations temporaires au repos dominical" sits before "Paragraphe 3 : Autres dérogations au repos dominical". Across the code, 5,691 of 11,433 paths (50%) have two consecutive levels with the same label (for example "TITRE V : ..." then "Titre V : ..."), so the header's last 3 levels often repeat a level.
- Note: the site shows today's version and the data is the 2025-07-13 snapshot, so the extra level may be a later update, not an extract flaw. The site is not the reference for structure.
- Open: collapse repeated levels in the header (keep the later, more specific one) or keep the path as is. Only the repetition inside the data justifies it. To be decided with the user and tested in 0c.
- Annexes: decided to keep them searchable. 0c compares as-is, excluded, and LLM-summary search.

## 2026-10-20: spot check 4 of 20 (R3232-8, L4162-4, L6362-12, L3132-25-3)
- Change: none in code. Manual comparison with legifrance.gouv.fr.
- Measured effect: article number, in-force date and text start match in all 4. Section paths: 1 of 4 identical (R3232-8); in the other 3 the data has extra levels. In each, the extra level is an older title of a level that the site shows under its current title (for example "Livre III : La formation professionnelle continue" then "Livre III : La formation professionnelle"). The site shows only the second of each pair.
- Reading: these renames predate the 2025-07 snapshot, so this is not a stale-snapshot effect. The extract seems to keep both the old and the new title (inference from 3 examples; the legal renaming history is unverified). This is likely the cause of the repeated levels (50% of paths) and favours keeping the later title if levels are collapsed.
- Decision (user): keep the path as is for now; test "collapse repeated levels" in 0c. More screenshot checks to come.

## 2026-10-20: check of the "old and new title" explanation
- Change: spot-check file split into checked / still to check / edge cases. `make verify` no longer overwrites it.
- Web (searched 2026-10-20): the ordonnance 2017-1389 of 2017-09-22 turned the "compte personnel de prévention de la pénibilité" into the "compte professionnel de prévention" (confirmed); the loi 2018-771 of 2018-09-05, art. 4, retitled Livre III of the sixth part "La formation professionnelle" (confirmed). Not found: the exact former chapter and book titles in force, the LEGI documentation on how title versions are stored, and the extract's own description of `texte_contexte`.
- Data: 749 articles have "Livre III : La formation professionnelle continue" in the path; only 298 of them also have the new title, 451 have the old title alone, none has the new one alone. The old title is not tied to article age (2008 to 2025). So the extract does not simply list old plus new titles; its path rule is unexplained.
- Consequence: collapsing repeated levels cannot remove stale titles that stand alone. Compare with the official LEGI dump or SocialGouv/legi-data if the explanation matters.

## 2026-10-20: spot check 9 of 20 and the rule behind repeated levels
- Change: none in code. Five more articles compared with legifrance.gouv.fr (R5123-8, L2262-8, R4451-6, D6331-71, D4626-5).
- Measured effect: number, in-force date and text match in all 9 checked articles. Paths: in every article where the data has repeated levels, the same level (Titre V, Chapitre Ier, Section 3, ...) appears 2 to 3 times in a row with different titles, and the site shows the LAST one (9 of 9, including the earlier three).
- Correction: the 451 articles with "Livre III : La formation professionnelle continue" alone are all in the Partie réglementaire, where the site still shows that title (D6331-71). They are not stale titles. The 298 with both titles are all in the Partie législative, where the 2018 law retitled the book.
- Reading: a level cannot nest inside a level of the same type, so two consecutive levels with the same label ("Section 3", "Section 3") are one node with several titles. The extract lists them oldest to newest. Rule to test in 0c: collapse each run of same-label levels and keep the last. Default stays "path as is" (user decision).

## 2026-10-20: spot check 14 of 20 and the collapse rule tested on 14 site paths
- Change: none in code. Five more articles compared with legifrance.gouv.fr (R7524-1, R4641-15, L7342-11, R5132-21, D1441-24-2). Site paths of all 14 checked articles saved in `tests/fixtures/legifrance_site_paths.json`.
- Measured effect: number, in-force date and (where visible) text match in all 14. Rule "collapse each run of same-label levels, keep the last" applied to the data path gives exactly the site path for 14 of 14 articles (for example 12 levels to 8, 10 to 7). One typographic difference: curly quotes with inner spaces in the data, straight quotes on the site.
- Limit: 14 articles, all read from screenshots at one date; the site shows today's version.
- Default unchanged (path as is); the rule is the header variant to test in 0c.
