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

## 2026-10-20: collapse-repeated-levels option and spot check 20 of 20
- Change: `collapse_repeated_levels` and a `collapse_repeats` option (default off) in `chunking/header.py`, passed through `ingest.build_chunks`. Six more seeded articles checked (L2363-12, D5132-10-2, L2362-9, L3123-9, L5426-8-3, R5324-1); site paths of all 20 stored with the data paths in `tests/fixtures/legifrance_site_paths.json`. 40 tests pass (22 new, one per site path).
- Measured effect on the site paths: the rule reproduces the Légifrance path exactly for 20 of 20 articles; in-force dates match in all 20; texts that were visible match.
- Measured effect on chunks, option on versus off (header style last_k, k=3): chunks 11,562 vs 11,563; header tokens median 54 vs 54, p90 71 vs 72; split articles 45 vs 46; total tokens 2,254,356 vs 2,256,934. The option changes which levels the header shows, not its size.
- Default unchanged. Quality effect to be measured in 0c.

## 2026-10-20: spot check finished (20 seeded + 8 edge cases)
- Change: none in code. Eight edge-case articles compared with legifrance.gouv.fr; their site paths added to `tests/fixtures/legifrance_site_paths.json` (28 in total).
- Measured effect: the collapse rule reproduces the Légifrance path in 28 of 28 articles. In-force dates match in 27 of 27 where a start date was visible (L1237-1 shows only "en vigueur au 20 octobre 2026"). Star number (R*3231-4), padded number (L1251-33-1) and the path with a carriage return (L2152-1) are confirmed as handled correctly.
- Difference: L6123-5 is in force since 2026-02-21 on the site, but 2024-01-01 in the data. The article changed after the 2025-07-13 snapshot, so the stored text may be outdated. This is the freshness gap that stage 6 would measure; the README and answers state the corpus date.
- Not verified: article texts of the 8 edge cases and of most seeded cases were not visible in the screenshots; only numbers, dates and paths were compared there.

## 2026-10-20: GDPR reader and chunker (Loop 2)
- Change: `sources/gdpr.py` (parser and profile), GDPR branches in `ingest.py` (header inputs, split order), `split.pack` fallback chain, `verify_gdpr`, CLI `profile|verify legi|gdpr`, fixture `tests/fixtures/gdpr_fr_excerpt.xhtml` (6 real units), `tests/test_gdpr.py` (11 tests; 59 tests in total).
  - Body: numbered paragraphs separated by a blank line, points and definition sub-points one per line, each definition row of Article 4 one group. Footnote markers dropped (their texts sit outside the articles). Recital label "(4)" removed.
  - Header: `RGPD (règlement (UE) 2016/679), article 5 : <title>. <chapter> > <section>.`; recital `RGPD, considérant 4.` (EN: GDPR / recital). Style last_k, k=3 as for the Code du travail.
  - Split rule above 1,024 tokens: pack whole paragraphs; a paragraph over the limit goes to points; a point over the limit goes to sentences. Paragraph or definition range stored in `extra["paragraphs"]`.
- Measured effect (FR): 99 articles, 173 recitals, 11 chapters, 15 sections (sections now verified), 58 articles under a section, 17 articles without numbered-paragraph blocks, one article (4) with nested definition tables. Article body tokens: median 345, p90 1,160, 15 over 1,024 (max 2,226); recitals median 175, max 842. 272 units give 292 chunks; 15 articles split; no chunk over 1,024 (max 1,023); no word-window fallback needed. EN: 281 chunks, 8 articles split, max 1,013.
- Difference from the spec's earlier measurement: token percentiles are slightly lower (max 2,226 vs 2,230) because footnote markers are removed.
- All checks pass (`make verify SOURCE=gdpr`), including FR and EN having the same ids and Article 5 having points a) to f) then paragraph 2.

## 2026-10-21: GDPR spot check
- Change: none in code. The user compared the 15 sampled units (10 articles, 5 recitals) with EUR-Lex by hand and judged it sufficient. Screenshots sent show only the document header, so I did not compare texts myself.
- EUR-Lex header: CELEX 32016R0679, JO L 119 of 4.5.2016, pp. 1-88, "Current consolidated version: 04/05/2016". Corrigenda handling not verified.
- Loop 2 approved by the user.

## 2026-10-21: Loop 3 split between machines
- Change: none in code. Decision (user): the bge-m3 vectors are computed on the Windows laptop (RTX 3060, 6 GB), not on the Mac. Handoff written in `docs/handoff/loop3_windows_embedding.md`, project rules in `CLAUDE.md`.
- Plan: the Windows session builds `legalrag embed` (output keyed by article_uid and chunk_index, with embed_text_hash), the Mac later creates the database and loads the vectors.

## 2026-10-22: fetch command for the raw data
- Change: `legalrag fetch` (`src/legalrag/fetch.py`, `make fetch`) downloads the four raw files and checks their SHA-256; handoff sections 5.1 to 5.3 rewritten with the exact access, fetch and processing steps. 3 new tests (62 in total).
- Measured effect: run against the real sources into an empty folder, all four files downloaded in about 6 seconds and matched the recorded checksums, so the upstream data is unchanged as of 2026-10-22. A second run reports `present` for all four. Building all chunks from the raw files gives 12,136 chunks with unique keys, max 1,023 tokens, in about 23 seconds and 1.8 GB peak memory on the Mac.

## 2026-10-22: Windows laptop setup and CUDA wheel (Loop 3)
- Change: `pyproject.toml` pins `torch` to the PyTorch CUDA 12.6 index (`pytorch-cu126`) on Linux only, and `torch` is listed in the `embed` extra so uv applies the pin. The Mac install is unchanged.
- Why: the default torch 2.14.1 wheel is built for CUDA 13.0; the laptop's Windows driver (546.30, CUDA 12.3) is too old for it, so `torch.cuda.is_available()` was False.
- Measured effect: with `2.14.1+cu126`, `torch.cuda.is_available()` is True on the RTX 3060 Laptop GPU (CUDA 12.6 wheel on a 12.3 driver, through minor-version compatibility), and a 2048x2048 fp16 matrix product runs on the GPU. 57 tests pass, 2 skipped (they need the raw data); ruff passes. About 5.3 GB of the 6 GB VRAM was free.
- Setup on this machine: WSL2 Ubuntu with 10 GB RAM (`.wslconfig`), `make`, `uv` 0.13.4, `gh` 2.103.0. Raw data not yet in place.

## 2026-10-22: bge-m3 embeddings computed (Loop 3)
- Change: `legalrag embed` (`src/legalrag/embed.py`, `make embed`), commits `a9d11d3` and `eaf6f4730`. bge-m3 dense, fp16, batch 16, `max_seq_length` 1100, shards of 1,000, chunks sorted longest first, vectors normalised in float32, run `main` (git commit in `run.json`: `eaf6f47`, clean tree). Output in `data/embeddings/` (gitignored).
- Measured effect (RTX 3060 Laptop 6 GB, torch 2.14.1+cu126, sentence-transformers 6.1.0, model revision 5617a9f6): trial of 200 evenly spaced chunks took 3 s, peak VRAM 1,451 MB. Full run: 12,136 chunks (11,563 + 292 + 281) in 97 s of embedding, 2 min 13 s wall including model load and chunk building, peak VRAM 1,491 MB (`torch.cuda.max_memory_allocated`), peak RAM 5.6 GB. No out-of-memory with the longest chunks first.
- Checks on the merged parquet: 12,136 rows, 12,136 unique keys, dimension 1,024, all finite, norms 0.9999998 to 1.0000001. Truncation: guarded by `token_count + 2 <= 1100` before the run; not re-measured on the model's own tokenizer output.
- Sanity (6 French questions, numpy cosine over all vectors, inspection only): "préavis de démission" L1237-1 first (0.651); "droit à l'effacement" GDPR art. 17 first (0.682); "durée légale du travail par semaine" L3121-27 first; "notification d'une violation de données" art. 33 first; "durée maximale de la période d'essai" L1221-19 first; "quand le consentement est-il valable ?" art. 7 first. The French and English art. 33 both rank in the top 2, since the vectors are not language-filtered.
- Sanity check now in the repo: `legalrag sanity` (`make sanity`, `src/legalrag/sanity.py`, 3 tests with a stub embedder; 73 tests in total). On the real file it prints 6 PASS, same scores as the scratch script. The 6 questions are short and share words with their articles, so a pass means "vectors not broken", not retrieval quality; realistic questions come in Loop 4 and step 0b.
- Device choice: `--device cuda|cpu|auto` on `embed` (default cuda) and `sanity` (default auto). CPU uses float32 instead of fp16. Measured: `sanity --device cpu` gives the same 6 PASS in 19 s wall on this machine (including model load); a full CPU embedding run was not timed. Not run on the Mac.
- Not done: the Mac side (database, load, index) is untouched.

## 2026-10-22: Mac check of the Windows embeddings (Loop 3)
- Change: none in code. Release `embeddings-bge-m3-main-v1` downloaded into `data/embeddings/` and compared with chunks rebuilt on the Mac from the raw files.
- Measured effect: both SHA-256 values match the release notes; 73 tests pass and ruff is clean on the Mac; `uv lock --check` is consistent. The Mac builds the same 12,136 keys as the file, and all 12,136 `embed_text_hash` values match, so both machines produce identical chunks. Vectors: 1,024 dimensions, all finite, norms 0.9999999 to 1.0000001, no all-zero rows, no duplicate vectors, one model revision (5617a9f6). Independent signal: the same GDPR chunk in French and in English has a median cosine of 0.865 (n=281, minimum 0.748). The two Code du travail articles with identical bodies (L1232-3, L1233-12) have cosine 0.849, since their headers differ.
- Not yet done: the sanity command on the Mac (needs torch there), the database part.

## 2026-10-22: database schema, loading and index (Loop 3, Mac side)
- Change: Alembic migration `0001` (schema A+: `corpus_versions`, `articles`, `chunking_runs`, `chunks`, `chunk_embeddings`), `config.py`, `db.py`, `store.py` (loaders), `dbcheck.py`, CLI `migrate`, `load-chunks`, `load-embeddings`, `db-check` and the matching `make` targets; dependency `pgvector` 0.5.1; 10 new tests against a throwaway database (83 in total).
  - `chunks.tsv` is a generated column: French dictionary for `lang = 'fr'`, English otherwise, computed from `embed_text` (header and body). `articles` also holds the recitals.
  - Chunking run name `default`; a run is immutable: other settings or changed chunk text under the same name are refused. Vectors are matched by (`article_uid`, `chunk_index`) and refused unless `embed_text_hash` equals the stored chunk hash.
  - HNSW index `chunk_embeddings_hnsw_bge_m3`: cosine, partial (`model = 'BAAI/bge-m3'`), pgvector defaults (m 16, ef_construction 64), built after the vectors load.
- Tested before building: a generated `tsvector` column with a `CASE` on the language is accepted by Postgres 16 (immutable expression). Finding for step 0c: the French dictionary stems "démission" to `démiss` but "démissions" to `dem`, so a plural query misses a singular text in keyword search.
- Measured effect (Mac, Docker `pgvector/pgvector:0.8.7-pg16`): `load-chunks` loaded 11,977 articles and 12,136 chunks in 26 s; a second run inserted 0. `load-embeddings` loaded 12,136 vectors and built the index in 11 s. All 10 `db-check` checks pass: counts, 1,024 dimensions, unit norms, hashes equal, no empty keyword vector, no orphan chunk, index exists, and the planner uses it (index scan, 0.77 ms for a top-5 query). Cross-language check from the stored vectors: for 285 of 292 French GDPR chunks (97.6%) the nearest English chunk is the same article or recital.
- Sizes: `chunk_embeddings` 162 MB including the 95 MB index, `chunks` 38 MB, `articles` 32 MB, keyword index 6 MB.
- Observed, not a design rule: a one-shot query with the model passed as a parameter still used the partial index. A prepared statement reused many times may build a generic plan that cannot; not tested.
- Not done: `make fresh-rebuild` (needs a drop of the database, to be confirmed with the user), the sanity check with the model on the Mac, Loop 4.

## 2026-10-22: stemming cases and index versus exact scan (measured for the 0c decisions)
- Change: none in code. Two measurements on the loaded database.
- French dictionary (`french_stem`), stems: démission -> `démiss`; démissions -> `dem`; démissionner -> `démission`; commission -> `commiss`; commissions -> `comm`; missions -> `mission`; finissions -> `fin`; licenciement(s) -> `licenci`; salarié(s) -> `salari`; contrat(s) -> `contrat`. Reading: words ending in "-issions" lose that ending as if they were a verb form like "finissions" (inference from these examples, the rule itself was not read). Singular and plural of most words still agree; the "-ission(s)" words do not.
- SUPERSEDED, WRONG (see "scaling measurements" below: the "exact" runs reused a cached plan, so they were not exact). Vector search, 100 random stored vectors as queries, top 10, same Python harness: HNSW index median 2.30 ms, exact scan (index off) median 1.01 ms; the index returned the same 10 chunks as the exact scan in 100 of 100 queries. At 12,136 vectors the index brings no speed gain; it is kept for larger corpora and the plan's production design. (The 0.77 ms in the entry above was the execution time inside the database, without the Python round trip.)

## 2026-10-22: scaling measurements and a correction (database)
- Change: none in code. Throwaway databases (created and dropped by the scripts) with the real chunk texts and vectors copied 1, 4 and 8 times (12,136, 48,544, 97,088 rows; each copy of a vector has noise added, cosine to the original about 0.89). Synthetic: copies of the same vocabulary and clustered vectors, so real growth with new topics would behave somewhat differently. Docker Postgres 16, pgvector 0.8.7, one machine, no parallel index build.
- Correction: the earlier "exact scan 1.0 ms, index brings no speed gain" was wrong. The Python library prepares a query after five runs and then reuses the cached plan, so the "exact" runs after the fifth silently used the HNSW plan (that is also why recall was exactly 1.000). The comparison below disables preparing (`prepare_threshold=None`) and checks the plan. Lesson: when comparing plans, never reuse a prepared statement.
- Vector search (top 10, 50 queries, median): exact scan 40 ms, 275 ms, 547 ms; HNSW (ef_search 40) 2.0 ms, 3.8 ms, 4.2 ms with recall@10 0.998, 1.0, 1.0 against the exact result. ef_search 400: 6.7, 14.8, 16.0 ms, recall 1.0, 1.0, 1.0. On the real table: exact 38 ms, HNSW 1.6 ms.
- Index build and size: HNSW build 9.8 s, 39.7 s, 79.0 s; size 94, 379, 758 MB (about 7.8 KB per vector). GIN build 0.3, 1.0, 2.1 s; size 2, 8, 16 MB. Table 15, 63, 126 MB.
- Keyword search: root of "licenciement" matches 468, 1,872, 3,744 chunks; count 0.71, 1.47, 2.43 ms; top 10 by ts_rank 1.0, 2.67, 5.25 ms. Rare word "démission": 33, 132, 264 matches; ranked 0.58, 0.71, 1.06 ms. Ranking cost follows the number of matches.
- Insert, 1,000 rows in one batch into the loaded table: both indexes 4.0 s, 5.1 s, 5.6 s; GIN only 0.25, 0.40, 0.26 s; no index 0.25, 0.26, 0.26 s. Single-row insert with both indexes: median 5.0, 5.9, 6.1 ms. The HNSW index accounts for almost all of the insert cost.
- Delete 1,000 rows: 11, 48, 23 ms. Table and index sizes did not change after the delete, nor after VACUUM (rows are marked dead; the files do not shrink). VACUUM took 18 s, 83 s, 0.3 s; the last value is unexplained (autovacuum may have run first, not checked).
- Memory: the first attempt asked for a 2 GB work area for the parallel index build and failed because Docker gives Postgres 64 MB of shared memory; that was my setting, not a need. The HNSW graph itself needs about its index size in memory (94 MB for the real data).

## 2026-10-24: load-chunks refuses a tree with uncommitted changes
- Change: `load-chunks` stops with exit code 1 when the git working tree is not clean; `--allow-dirty` loads anyway and the stored `code_version` carries the flag. `embed.DIRTY` names the flag text. 3 new tests (86 in total).
- Why: the run `default` was stored with `code_version` `7799a18… (uncommitted changes)`, because the loader was not committed yet when it ran. A stored run is never changed, so its `code_version` should name the exact commit. The data itself is right (its chunk fingerprints match the Windows embedding run exactly); only the provenance record is imprecise, and it stays as it is.

## 2026-10-24: known limits of the splitters (to check in step 0c)
- Change: none in code; a note for debugging. If the evaluation shows weak retrieval on split articles, look at these first and re-split (a new chunking run).
- `split_sentences` cuts at `.`, `!` or `?` + whitespace + capital letter or digit, except after a single capital letter or a listed abbreviation. Read from the code, not measured on the data: the word before the stop is taken up to the last space, so "l'art." and "(art." are not recognised and are cut; "Mme." and "MM." are not on the list; a sentence starting with a lowercase letter is never cut.
- GDPR `paragraphs` note: a chunk that starts inside a paragraph (a split paragraph) lists only the numbers it begins paragraphs with, so the range can miss that paragraph; a chunk made only of points "(a)", "(b)" gets no note.
- Last-resort word windows (`word_windows` flag) are the lowest-quality cuts; check whether those chunks retrieve worse.

## 2026-10-26: migration 0002 and delete-run (database)
- Change: migration `0002` adds `CHECK` constraints (`lang` in fr/en on articles and chunks; `kind` in article/recital/annex on articles) and `ON DELETE CASCADE` on `chunks.run_id`. New command `legalrag delete-run NAME` prints how many chunks and vectors would go and asks before deleting (`--yes` skips the question); articles stay. 4 new tests (90 in total).
- Why: free-text `lang` would let a typo like `FR` get English stemming in the generated `tsv` column; removing a chunking run needed two hand-ordered deletes.
- Checked: the stored values fit the constraints (lang fr/en; kind article, recital, annex), so 0002 applied to the real database without changes to the data; downgrade then upgrade on a throwaway database ended at `0002`; the 10 `db-check` checks still pass. `delete-run` was run for real only on an unknown name (refused); deleting an existing run is covered by a test on a throwaway database, not done on `default`.
- Decided with the user: `valid_to` 2999-01-01 stays as in the source for now.

## 2026-10-26: cross-language check made exact, new index recall check (database)
- Change: `cross_language_rate` (check 10) now searches without the vector index (`SET LOCAL enable_indexscan = off` around the loop). New check 11 `index_recall`: for a fixed pseudo-random sample of 100 stored vectors (ordered by `md5(id)`), the share of the exact 10 nearest chunks (the probe itself excluded) that the index also returns, passing at 98% or more. 11 checks in total; 92 tests.
- Why: with the index, the language filter (`lang = 'en'`) is applied to the short candidate list the index returns (`hnsw.ef_search` 40), which can hold no English chunk. Check 10 then reported 285/292 = 97.6%, mixing the model's quality with the index's limit.
- Measured (French GDPR chunk -> nearest English chunk, 292 queries, prepared statements off): default 5 empty results + 2 wrong unit = 285/292; `ef_search` 100: 286; 400 and 1000: 289; iterative scan `strict_order`: 285 (7 wrong, unexplained); iterative scan `relaxed_order`: 289; exact scan: 289/292 = 99.0%. Time per query: exact 5.2 ms, index 1.0 to 1.2 ms, `ef_search` 1000 5.2 ms. The 3 misses under exact search are art_4 -> art_3, art_57 -> art_58, rct_150 -> art_83 (not investigated). `hnsw.iterative_scan` exists in the installed pgvector 0.8.7 and is `off` by default.
- Measured on the real data: check 10 exact 289/292 = 99.0% in 1.8 s; check 11 998/1000 = 99.8% in 5.9 s.
- Not verified: the candidate-list explanation is inferred from the settings comparison (longer list or iterative scan removes the empty results); the candidate list itself was not inspected.
- For step 0c: any search with a language filter has the same limit; try `SET LOCAL hnsw.iterative_scan = relaxed_order` first (it matched the exact result here at the default speed).

## 2026-10-26: ANALYZE after loading vectors; fresh rebuild (database)
- Change: `load-embeddings` runs `ANALYZE` after building the index (`store.analyze`). New `make fresh-rebuild` (`scripts/fresh_rebuild.py`): builds a scratch database from migrations, `fetch all`, the vectors downloaded from the GitHub Release (SHA-256 compared with `data/embeddings`), `load-chunks`, `load-embeddings`, `db-check`; compares row counts, article and chunk fingerprints, the mean vector and the schema version with the real database; drops the scratch database. The real database is only read. 93 tests.
- Found by the first rebuild: right after loading, check 9 (planner uses the HNSW index) failed in the scratch database (plan `Limit (cost=833.66..833.67 rows=1)`). Tables had never been analysed (`last_analyze` and `last_autoanalyze` empty), so the planner worked from guessed row counts. After a manual `ANALYZE` the same database passed (`Limit (cost=287.46..313.61 rows=5)`). The real database passed only because autovacuum had analysed it in the days since the load.
- Why it matters: searches right after a load could run a slow plan. `ANALYZE` after a bulk load is the usual practice.
- Result of `make fresh-rebuild` after the fix (about 54 s): all 11 checks pass in the scratch database; row counts (3, 11,977, 1, 12,136, 12,136), article fingerprint, chunk fingerprint, mean vector and schema version (`0002`) are identical to the real database. Index recall differs a little between builds (998, 1000 and 999 of 1,000 in three builds), as an HNSW graph is not built the same way twice. The scratch database was dropped; leftover cleanup of 2026-10-26: container `pgv-test` with its volume and the empty database `legalrag_test_b7cd0a35` were removed.

## 2026-10-27: smoke retrieval (Loop 4)
- Change: new command `legalrag smoke` / `make smoke` (`src/legalrag/smoke.py`, `tests/smoke_questions.yaml`): embeds 29 hand-written questions with bge-m3 (no instruction prefix: the model card says bge-m3 does not need one), prints the nearest 5 chunks of run `default` (cosine, no filter) and marks the expected articles; it warns when an expected label is not in the database. `pyyaml` added as a dependency. On macOS, torch is limited to below 2.12 (`[tool.uv] constraint-dependencies`): 2.12 and later have macOS wheels for macOS 14 only, and this Mac runs macOS 12; torch 2.11.0 is installed. 100 tests.
- Questions: drafted from scratch (23), then merged with ideas from BSARD (everyday wording, several relevant articles per question), Ragas (single-hop or multi-hop, specific or abstract), CRAG and UAEval4RAG (false premise, underspecified, out of database), the Harvard Open French Law RAG study (English question over French law) and LegalBench-RAG (precise passages). Seven groups A to G. Every expected article was looked up in the database and read, except art. 3 (not opened) and the expected chunk of art. 4, 83 and R2312-9.
- Result (details and the six misses in `docs/data_profiles/smoke_notes.md`, output in `smoke_output.txt`): expected article in the top 5 for 21 of 27 questions; first rank 1 for 14, rank 2 for 5, rank 3 for 1, rank 4 for 1. Misses: Q6 (rupture conventionnelle in everyday words), Q8 (exact article number), Q11 (annex table), Q13 (personal dismissal steps), Q22 (GDPR outside the EU), Q25 (e-mail monitoring, two sources).
- Also seen: French questions get 8 English GDPR chunks in their top 5 lists; a long annex fills 4 of the 5 places for Q12; top-1 distance is above 0.40 for all of the three misses Q6, Q11, Q25 and the two unanswerable questions (0.445, 0.459), and at most 0.383 where an expected article was found.
