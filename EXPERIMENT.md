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
- SUPERSEDED, see the next entry (Q25 was an index artefact; 22 of 27 with the corrected setting). First result (details in `docs/data_profiles/smoke_notes.md`, output in `smoke_output.txt`): expected article in the top 5 for 21 of 27 questions; first rank 1 for 14, rank 2 for 5, rank 3 for 1, rank 4 for 1. Misses: Q6 (rupture conventionnelle in everyday words), Q8 (exact article number), Q11 (annex table), Q13 (personal dismissal steps), Q22 (GDPR outside the EU), Q25 (e-mail monitoring, two sources).
- Also seen: French questions get 8 English GDPR chunks in their top 5 lists; a long annex fills 4 of the 5 places for Q12; top-1 distance is above 0.40 for all of the three misses Q6, Q11, Q25 and the two unanswerable questions (0.445, 0.459), and at most 0.383 where an expected article was found.

## 2026-10-27: smoke results reread in full; index setting for query vectors
- Change: `smoke.nearest` sets `hnsw.ef_search` to 100 for its query (`smoke.EF_SEARCH`; 1 test assertion added). `smoke_output.txt` and `smoke_notes.md` rewritten after reading the full text of every retrieved chunk and of the expected articles that did not come back.
- Found: with pgvector's default `ef_search` 40, Q25 returned a top 5 different from the exact top 5 (exact scan: D4163-32, R4722-12, D7342-6, art. 88 fr 0.423, art. 88 en 0.423; index: D4163-32, R4722-12, D4163-4, R4722-13, R4446-3), so Q25 looked like a total miss. Over the 29 question vectors, index against exact scan: top 5 recall 142/145 = 97.9% at `ef_search` 40 (question 25 differs), 145/145 at 100, 200 and 400; top 10 recall 284/290 = 97.9% at 40 (questions 8, 19, 25 differ), 290/290 at 100, 200 and 400.
- Check 11 (`index_recall`) uses stored vectors as probes and reported 998 to 1000 of 1,000; question vectors, which are not in the graph, did worse at the default setting. The check is optimistic for real queries: to revisit (probes that are not stored vectors, or the query setting).
- Result with `ef_search` 100: expected article in the top 5 for 22 of 27 questions (first rank: 14 at rank 1, 8 at ranks 2 to 4, 5 not found: Q6, Q8, Q11, Q13, Q22). Other things the reading showed: the first version's explanation of Q6 was incomplete (the header is not the main cause: L1237-11 0.478 with the header and 0.480 without; L1237-17 0.414 and 0.441), Q10 rank 1 (L2312-36) is as good an answer as the expected article, Q20 rank 1 (L8115-3) answers the question as written, Q16/Q21 top 5 are on topic, and the SMIC question returns other euro amounts (D5122-13, D5522-16, D5424-74).
- For step 0c: choose and set the query-time `ef_search` (per query with `SET LOCAL`, or per database); review the expected lists listed at the end of `smoke_notes.md` before they become an evaluation set.

## 2026-10-27: smoke expected lists changed; flaky test fixed
- Change: `tests/smoke_questions.yaml`: L2312-36 added to Q10, L1232-1 to Q13, recital 66 to Q15, recital 155 to Q25. Q16, Q20, Q21 left for the evaluation set design in 0b (primary article and also-acceptable ones). Retrieved chunks are identical to the previous run; only the marking changed: expected article in the top 5 for 23 of 27 questions (15 at rank 1, 8 at ranks 2 to 4, 4 not found: Q6, Q8, Q11, Q22).
- Test fix: `test_analyze_gives_the_planner_row_counts_after_a_load` failed once in a full run and not in 31 later runs. It asserted that the table had never been analysed; autovacuum can analyse the empty test table once earlier tests have inserted and rolled back enough rows (cause inferred, the failure output was not captured). The assertion was dropped; the one that matters (the row count after `ANALYZE`) stays.

## 2026-10-28: evaluation code and dense baseline on the dev half (Loop 5, step 0b)
- Change: `src/legalrag/metrics.py` (Hit@5, Recall@5/10/20, MRR@10 on the first primary article, nDCG@5/10 with the grade as gain, bootstrap by cluster, paired difference for 0c), `src/legalrag/evaluate.py` (exact dense search with the question's language filter, chunks merged to articles by best chunk, top 20 articles), `legalrag eval` / `make eval`. The test half needs `--final`. Articles with the same body as a gold article count as that gold article; a second twin of a matched article leaves the ranking.
- Check: our metrics agree with `ir_measures` (trec_eval) on 40 random rankings for all 7 measures (`tests/test_metrics.py`); `RR(rel=2)` is the primary-article MRR, `nDCG` is linear gain.
- Measured (dev half, 61 questions with gold in 40 clusters, `eval/gold.jsonl` sha256 78cc06a4, run `default`, bge-m3, exact search, 2000 resamples): nDCG@10 0.738 [0.651-0.821], Recall@10 0.893 [0.815-0.956], Hit@5 0.902 [0.815-0.968], Recall@5 0.800, Recall@20 0.926, MRR@10 0.670 [0.567-0.768], nDCG@5 0.702 [0.603-0.796].
- By group (dev): A plain lookups nDCG@10 0.806 (17 q); B lay wording 0.685 (15 q); E GDPR in French 0.586 (5 q, interval 0.19-0.96); I ministry headings 0.743 (15 q). Groups C, D, G, H have 1 to 3 questions each: no reading.
- Six questions have no gold article in the top 5: a cross-border transfer question in lay words (art 15 at rank 13), the CSE delegation size (R2314-1 at rank 7, the ranking is filled with delegate rules), the striking employee (L2511-1 not in the top 20, other strike articles come first), the access-request deadline (art 12 not found, recital 59 at rank 8), the exact article number "L1221-13" (not found), GDPR scope for a non-EU company (art 3 at rank 17, recital 23 not found).
- Not done: test half (kept for the end of the stage), no comparison between runs yet. The intervals are wide (60 questions): a change smaller than about 0.05 nDCG@10 cannot be told from noise on one half, so 0c comparisons use the paired difference.

## 2026-10-29: Syntec sanity run (step 0b)
- Change: `scripts/sanity_syntec.py` scores bge-m3 (exact cosine search, no database) on Syntec, 90 articles of a collective agreement and 100 French questions with one gold article each, using `legalrag.metrics`. Files read from outside the repo; Syntec has no stated licence.
- Measured (CPU, 53 clusters, 2000 resamples): nDCG@10 0.845 [0.788-0.899], nDCG@5 0.841, MRR@10 0.806 [0.738-0.871], Hit@5 0.950, Recall@10 0.960, Recall@20 0.990.
- Cross-check with the official `mteb` 2.26.28 `SyntecRetrieval` task (bge-m3 revision 5617a9f6, run with `uv run --with mteb`, nothing added to the project): nDCG@10 0.84505, nDCG@5 0.84149, MRR@10 0.80583, Recall@5/10/20 0.95/0.96/0.99. Ours match to the third decimal on all of them. The MTEB-French paper (arXiv 2405.20468, table 11) lists 0.85 for bge-m3 (read from a page summary).
- BSARD (222 test questions, 22,633 articles, CC BY-NC-SA 4.0): `scripts/sanity_bsard.py` and `docs/handoff/bsard_windows.md` are written and the script ran in `--smoke` mode on the Mac (10 questions, 300 articles). Paper baselines for context: Recall@100 51.3 for BM25, 74.8 for the best baseline (unverified, from search summaries).
- BSARD full run on the Windows laptop (RTX 3060, bge-m3 5617a9f6, dataset revision f3ca6a39, 22,633 articles of which 504 cut at 1,100 tokens, 222 test questions, exact cosine, 2000 resamples of questions). Question alone: nDCG@10 0.309 [0.266-0.351], Hit@5 0.509 [0.446-0.577], Recall@10 0.386, Recall@20 0.468, MRR@10 0.364 [0.313-0.417], Recall@100 0.632 [0.579-0.685], Recall@200 0.699, Recall@500 0.787. Question plus `extra_description`: nDCG@10 0.292 [0.250-0.333], Recall@100 0.612 [0.561-0.664], Recall@500 0.765; the two variants overlap, so no clear difference. Vectors checked on the Mac: shape 22633x1024, no NaN, unit length, ids unique. Files kept in `data/external/bsard_out/full/` (not in git, licence CC BY-NC-SA 4.0).
- Reading: zero-shot dense search lands between the BM25 and best-baseline Recall@100 of the paper, with a small hit rate in the top 5 because each question has several relevant articles (4.8 on average). No sign of a harness fault (nothing near 0 or 1); this does not prove the metrics right on BSARD, the Syntec/mteb match does that.

## 2026-10-29: chunking variants prepared for the Windows laptop (step 0c)
- Change: `src/legalrag/variants.py` names the variants (`default`, `header-none`, `header-label`, `header-full`, `header-collapse`, `size-512`; each changes one setting). `embed`, `load-chunks` and `load-embeddings` take `--variant`; `make embed-variants` and `make pack-variants` (dry run, `ARGS=--publish` creates the release `embeddings-bge-m3-variants-v1`). Handoff: `docs/handoff/variants_windows.md`. The baseline keeps its names (`bge-m3-main`, chunking run `default`). Overlap between chunks is not implemented, so it is not a variant.
- Measured on the Mac (chunking only, no vectors): chunks default 12,136; header-none 12,117; header-label 12,123; header-last2 12,134 (added the same day, the plan D6 lists "last 2"); header-full 12,160; header-collapse 12,135; size-512 12,885.
- Confound: a longer header leaves less token budget, so long articles split at other points: articles split into several chunks are 69 (default), 58, 61, 83, 68 for the four header variants, and 442 for size-512. A header comparison therefore also moves a few chunk boundaries.
- Tests: 171 pass, ruff clean.

## 2026-10-29: keyword search and fusion against the dense baseline, dev half (step 0c, experiment A)
- Change: `src/legalrag/keyword.py` (BM25, k1 1.2, b 0.75, over the lexemes Postgres already stores in `chunks.tsv`, query through the same french or english configuration), `evaluate.fuse` (reciprocal rank fusion, k 60, top 100 articles of each list, optional weight on the keyword list), `legalrag eval --search dense|keyword|hybrid --keyword-weight`, `legalrag compare BASE OTHER` (paired difference, decision 3b verdict, per group). No new embeddings.
- Runs (dev, 61 questions with gold in 40 clusters, chunking run `default`, code commit 3e5ef49, gold sha 78cc06a4). Four settings were tried; they were fixed before the runs except the two weights, chosen after seeing that weight 1 hurt:

| Run | nDCG@10 | Recall@10 | Hit@5 | MRR@10 | nDCG@10 minus baseline [95% paired] |
|---|---|---|---|---|---|
| baseline (dense) | 0.738 | 0.893 | 0.902 | 0.670 | |
| keyword only | 0.548 | 0.697 | 0.656 | 0.505 | -0.190 [-0.300, -0.091] |
| hybrid, keyword weight 1 | 0.701 | 0.857 | 0.869 | 0.639 | -0.037 [-0.118, +0.036] |
| hybrid, keyword weight 0.5 | 0.716 | 0.877 | 0.885 | 0.638 | -0.022 [-0.090, +0.038] |
| hybrid, keyword weight 0.25 | 0.749 | 0.902 | 0.902 | 0.680 | +0.011 [-0.041, +0.060] |

- Verdict by decision 3b: no hybrid is an improvement (nDCG@10 is not clearly up in any); keyword alone is clearly worse (nDCG@10 and Recall@10 both clearly down). Weight 0.25 gives Recall@10 +0.008 [0.000, +0.027] and group A (plain lookups, 17 questions) nDCG@10 +0.053 [+0.006, +0.118]; with weight 1 group I (ministry headings, 15 questions) loses 0.210 [-0.337, -0.085].
- Where it helps and hurts: keyword alone finds the exact article number "L1221-13" at rank 2 where dense does not find it in the top 20, but fusion with the dense list brings it to rank 10 (weight 1) or loses it (weights 0.5, 0.25), because a list that only one search holds scores too little. GDPR scope question (smoke-22) moves from rank 17 to 2 (weight 1) and 5 (weight 0.25). Hurt: heading-style questions (sheet-14 rank 2 to 11, sheet-22 2 to 12) and hw-04 (5 to 19) with weight 1.
- Read with care: four comparisons on one 61-question half, the 0.25 gain is inside the noise. The test half has not been opened.

## 2026-10-29: reranker, heading styles and chunk limit against the baseline, dev half (step 0c)
- Vectors of the six variants come from the Windows laptop (Release `embeddings-bge-m3-variants-v1`, commit 6c7b6cb, all 12 SHA-256 equal to the release notes, chunk counts equal to the Mac's). Each variant is its own chunking run; `db-check` passes except the approximate-index recall check (97.4% header-none, 96.5% header-label, 95.1% header-collapse against 98%), which does not touch evaluation (exact search) but matters for the production index settings. Evaluated with `legalrag eval --run V --name V` at commit 9dbdeeb, clean tree, same gold (sha 78cc06a4), same dense exact search and embeddings model.
- Heading style and chunk limit (dev, 61 questions in 40 clusters; difference to the baseline `last_k` k=3, 1,024 tokens):

| Variant | nDCG@10 | Recall@10 | Hit@5 | nDCG@10 minus baseline [95% paired] |
|---|---|---|---|---|
| baseline (last 3 levels, 1,024) | 0.738 | 0.893 | 0.902 | |
| header-none | 0.667 | 0.852 | 0.820 | -0.071 [-0.129, -0.013] |
| header-label (article label only) | 0.678 | 0.829 | 0.770 | -0.060 [-0.115, -0.003] |
| header-last2 | 0.731 | 0.869 | 0.869 | -0.007 [-0.045, +0.031] |
| header-full (whole path) | 0.712 | 0.885 | 0.885 | -0.026 [-0.066, +0.015] |
| header-collapse (repeated levels merged) | 0.740 | 0.869 | 0.885 | +0.003 [-0.021, +0.028] |
| size-512 | 0.740 | 0.885 | 0.885 | +0.002 [-0.031, +0.042] |

- Reading: without section titles the dense search is clearly worse (header-none and header-label); between 2 levels, 3 levels, the whole path, merged levels and a 512-token limit no difference can be told from noise. None is an improvement by decision 3b, so the baseline settings stay. The header variants also move a few chunk boundaries (see the 2026-10-29 entry on variants). Not tried: the LLM-written heading sentence.
- SUPERSEDED on 2026-10-31 (annex label bug and a 1,024-token window that cut long chunks; see the 2026-10-31 entry): Reranker `BAAI/bge-reranker-v2-m3` (Apache-2.0) re-ordering the top 50 dense articles, article score = best chunk, CPU: nDCG@10 0.776 [0.686-0.854], Recall@10 0.885, MRR@10 0.731, Hit@5 0.885; minus baseline: nDCG@10 +0.038 [-0.038, +0.109], MRR@10 +0.062 [-0.044, +0.164], Recall@10 -0.008 [-0.067, +0.053]. Not clearly better, not an improvement by decision 3b. Group A +0.083, B +0.073, E +0.192 (5 questions), C -0.540 and D -0.264 (2 and 1 questions). The run took about 45 minutes with the model download and other jobs on the same CPU, so it is not a latency measurement; the run file records commit 9dbdeeb although the run started on an earlier commit (settings are written at the end; the bge reranker path did not change). Rerun for latency still to do.
- Environment: the Mac disk was 94% full and iCloud had replaced compiled files of `.venv` and two files of `data/raw` with `.icloud` stubs (numpy and tokenizers imports broke, 2 tests skipped). The project folder now lives in `~/Downloads/legal-rag-eval-fr` (not synced) with a symlink at the old `~/Documents/2026/` path; `.venv` rebuilt with `uv sync --extra embed --reinstall`; 160 tests pass.

## 2026-10-31: rerankers rerun after three faults, dev half (step 0c)
- Faults found in the first reranker run, all fixed before this rerun:
  - Annex labels were mapped back to the wrong kind (`split_label`), so the 8 annexes had no text and ranked last. The dev question smoke-12 (gold article an annex) fell from nDCG@10 1.0 to 0.0, which explains most of the old group C result. Fixed in 56cf7c3.
  - The 1,024-token window cut the end of long chunks: 17 to 49 of 12,136 chunks for bge, 167 to 188 for Qwen. Windows are now 1,152 (bge) and 1,700 (Qwen); no chunk of the default run is cut with the longest gold question, and the run record carries `truncated_pairs` (0 in both runs below). Fixed in 835464e.
  - Qwen loaded in bfloat16, very slow on this CPU (8.5 s for one 600-token pair, against 1.2 s in float32); it also computed the output scores of all 151,936 words at every position, and did not sort pairs by length. A first Qwen run was stopped after 14 hours 53 minutes. Fixed in afc55c9; new scores equal the old method within 2e-6 on 5 pairs.
- Setup: dense top 50 articles re-ordered, article score = best chunk, Mac CPU, dev half (61 questions in 40 clusters), clean commits.

| Run | nDCG@10 | Recall@10 | Hit@5 | MRR@10 | nDCG@10 minus baseline [95% paired] | Recall@10 minus baseline |
|---|---|---|---|---|---|---|
| baseline (dense) | 0.738 | 0.893 | 0.902 | 0.670 | | |
| bge-reranker-v2-m3 | 0.793 | 0.902 | 0.902 | 0.748 | +0.055 [-0.006, +0.120] | +0.008 [-0.035, +0.067] |
| Qwen3-Reranker-0.6B | 0.799 | 0.943 | 0.918 | 0.752 | +0.061 [+0.003, +0.125] | +0.049 [+0.008, +0.105] |

- Verdict by decision 3b: bge is not an improvement (nDCG@10 interval includes 0). Qwen is an improvement (nDCG@10 clearly up, Recall@10 not down), but its lower bound is +0.003. Qwen minus bge: nDCG@10 +0.006 [-0.053, +0.063], not distinguishable. Passing the rule while the other does not is not itself a difference between the two.
- Groups: Qwen against the baseline, group A +0.097 [+0.012, +0.200] (17 questions), C -0.185 (2 questions), D -0.046 (1 question); the others inside the noise.
- Time per question on the Mac CPU: bge 36.1 s; Qwen 91.2 s. The Qwen run shared the CPU with a heavily swapping Mac (9 to 10 GB of swap), so it is an upper bound, not a clean latency. Dense search alone takes about 0.3 to 0.4 s.
- Read with care: several comparisons on one 61-question half, the Qwen gain barely clears zero. Candidate depth is checked in the full-matrix section below (no shortage). The test half has not been opened.
- Embedding model `Qwen/Qwen3-Embedding-0.6B` (Apache-2.0) instead of bge-m3, same chunks (default chunking, 12,136), same exact dense search; vectors from the Windows laptop (Release `embeddings-qwen3-embedding-0.6b-v1`, commit 835464e, RTX 3060, 933 s, both SHA-256 equal to the release notes); questions embedded with the model's `query` prompt, chunks without an instruction. Dev half, run `qwen3` at a clean commit:

| Run | nDCG@10 | Recall@10 | Recall@20 | Hit@5 | MRR@10 | nDCG@10 minus baseline [95% paired] |
|---|---|---|---|---|---|---|
| baseline (bge-m3) | 0.738 | 0.893 | 0.926 | 0.902 | 0.670 | |
| Qwen3-Embedding-0.6B | 0.770 | 0.870 | 0.880 | 0.885 | 0.732 | +0.033 [-0.036, +0.106] |

- Verdict by decision 3b: not an improvement (nDCG@10 not clearly up). Recall@10 -0.024 [-0.094, +0.044] and Recall@20 -0.046 [-0.122, +0.018] are not clearly down either, but both point down while MRR@10 points up (+0.062 [-0.020, +0.147]): Qwen puts hits higher and misses more of them at depth. Groups: E +0.200 (5 questions), A +0.062, I -0.040, all inside the noise. Search time 0.052 s per question (query embedding time not included). The baseline model stays.

## 2026-10-31: full matrix of embedding model and reranker, dev half (step 0c)
- The two missing cells were run on the Qwen3-Embedding candidates (top 50 articles), same code and windows as above, `truncated_pairs` 0 in both run records. Dev half, Mac CPU.

| Embedding model | Reranker | nDCG@10 | Recall@10 | Recall@20 | Hit@5 | MRR@10 | nDCG@10 minus baseline [95% paired] | Seconds per question |
|---|---|---|---|---|---|---|---|---|
| bge-m3 | none (baseline) | 0.738 | 0.893 | 0.926 | 0.902 | 0.670 | | 0.3 to 0.4 |
| bge-m3 | bge-reranker-v2-m3 | 0.793 | 0.902 | | 0.902 | 0.748 | +0.055 [-0.006, +0.120] | 36.1 |
| bge-m3 | Qwen3-Reranker-0.6B | 0.799 | 0.943 | | 0.918 | 0.752 | +0.061 [+0.003, +0.125] | 91.2 (upper bound) |
| Qwen3-Embedding | none | 0.770 | 0.870 | 0.880 | 0.885 | 0.732 | +0.033 [-0.036, +0.106] | 0.05 |
| Qwen3-Embedding | bge-reranker-v2-m3 | 0.799 | 0.923 | 0.934 | 0.918 | 0.743 | +0.062 [-0.002, +0.128] | 35.3 |
| Qwen3-Embedding | Qwen3-Reranker-0.6B | 0.792 | 0.918 | 0.934 | 0.885 | 0.746 | +0.054 [-0.004, +0.120] | 77.2 |

- Verdict by decision 3b: only bge-m3 with Qwen3-Reranker is an improvement, and its lower bound is +0.003. The two new cells are not (intervals touch 0).
- On the Qwen3-Embedding candidates, Qwen3-Reranker minus bge-reranker is -0.007 [-0.064, +0.049]: not distinguishable, as on the bge-m3 candidates (+0.006). With a reranker, the choice of embedding model makes no clear difference.
- Six cells on one 61-question half make a lucky result likely; the single cell that passes is not evidence of a real gain.
- Decision for the retrieval default: dense bge-m3 without reranker. The reranker stays a measured option; its cost is 100 to 250 times the dense search on this CPU, and no clean GPU latency exists yet.
- Candidate depth checked: the 400 chunks searched hold at least 363 distinct articles per dev question with bge-m3 (median 398) and at least 367 with Qwen3-Embedding (median 399), so the 50 candidates are always available. The test half is not opened.

## 2026-10-31: annexes and language handling, dev half (step 0c)
- Annexes: ablation closed without a run (user decision). The corpus has 8 annexes; among the dev questions only smoke-12 has an annex in its baseline top 20 (it is the gold article, rank 1, nDCG@10 1.0), so excluding annexes could only lower the dev score and the summarised arm could change one question. Annexes stay searchable as they are. `scripts/judge_gold.py` is not affected by the earlier label bug: the two annex gold questions (smoke-11 test, smoke-12 dev) are in none of the judge outputs.
- Language handling: `legalrag eval --no-language-filter` searches the chunks of every language and merges the translations of an article into one result (dense only). Same embeddings and chunks, no new vectors. Dev half, run `nolang`:

| Run | nDCG@10 | Recall@10 | Recall@20 | Hit@5 | MRR@10 | nDCG@10 minus baseline [95% paired] |
|---|---|---|---|---|---|---|
| baseline (filter on the question's language) | 0.738 | 0.893 | 0.926 | 0.902 | 0.670 | |
| no language filter | 0.735 | 0.893 | 0.926 | 0.885 | 0.660 | -0.002 [-0.009, +0.003] |

- Verdict by decision 3b: not an improvement. 11 of 65 rankings differ (the GDPR questions, where English chunks join the results); nDCG@10 changes by at most -0.144 on one question (smoke-21) and +0.106 on another (mw-073). The filter stays.
- Limits: all 65 dev questions are French, so the dev half cannot show what the filter does for English questions (2 English questions are in the test half). Not tried: the approximate index with an iterative scan under the filter, because evaluation uses the exact scan.

## 2026-11-01: article-number rule, dev half (step 0c)
- Rule (`src/legalrag/articlenum.py`, flag `--article-lookup`, off by default): a question that names a Code du travail article by number (`L1221-13`, `R*3231-4`) gets that article first, found by its number in the articles table; the search results follow below it without repeating it. GDPR articles count only when the question names the RGPD or GDPR ("article 17" alone is ignored), and recitals by "considérant" or "recital". Option chosen by the user (direct lookup, not keyword search).
- Dev half, run `artnum` (dense search plus the rule), clean commit: nDCG@10 0.754 against 0.738, +0.016 [+0.000, +0.056]; Hit@5, Recall@5/10/20 and MRR@10 each +0.016 [+0.000, +0.056]. Only 1 of 65 rankings changes: smoke-08 ("Que dit l'article L1221-13 du code du travail ?") goes from rank outside the top 5 to rank 1.
- Verdict by decision 3b: not an improvement (interval touches 0). One question cannot show a gain; the rule is kept as a design choice for a known failure class, not as a measured win. The GDPR and recital patterns have unit tests but no dev question exercises them. How many test-half questions name an article is not counted; that half stays closed until the final run.

## 2026-11-02: query rewriting, dev half (step 0c)
- Rewrite: `deepseek-flash`, thinking off, temperature 0, one question per call, prompt `rewrite.v1` (`prompts/query_rewrite.yaml`: restate the question in the wording of the code, keep every detail, no article numbers, one sentence of at most 40 words, copy it if already legal). Script `scripts/rewrite_questions.py`; the 65 dev questions cost 0.0033 USD. A rewrite that is empty or names an article is not used (the original question is searched): 1 case, smoke-08. 54 questions are searched with a rewrite that differs from the question, 11 unchanged. Curly apostrophes are turned back to straight ones.
- Two ways to use it, dense bge-m3, same chunks, `legalrag eval --rewrites FILE --rewrite-mode replace|fuse`: replace searches the rewrite instead of the question; fuse runs both searches (top 100 articles each) and merges them by reciprocal rank fusion (k 60), as in the keyword fusion.

| Run | nDCG@10 | Recall@10 | Recall@20 | Hit@5 | MRR@10 | nDCG@10 minus baseline [95% paired] |
|---|---|---|---|---|---|---|
| baseline (original question) | 0.738 | 0.893 | 0.926 | 0.902 | 0.670 | |
| rewrite, replace | 0.726 | 0.888 | 0.943 | 0.885 | 0.675 | -0.011 [-0.060, +0.040] |
| rewrite, fuse | 0.748 | 0.910 | 0.959 | 0.918 | 0.688 | +0.010 [-0.022, +0.045] |

- Verdict by decision 3b: neither is an improvement (nDCG@10 not clearly up). Fuse minus replace +0.021 [-0.010, +0.051]. Fuse raises Recall@20 by +0.033 [+0.000, +0.080], which matters only as a candidate list for a reranker.
- By who wrote the question (mean nDCG@10 change, fuse; replace in brackets): ministry sheets +0.075 (+0.077) over 15 questions, model-written +0.001 (-0.053) over 30, smoke -0.024 (-0.010) over 12, hand-written -0.062 (-0.039) over 4. Group I (the sheets): fuse +0.075 [+0.010, +0.154], replace +0.077 [-0.002, +0.184]. One subgroup of eight, looked at after the result: exploratory, not a finding.
- Hypothesis, written down before the test half is opened: rewriting helps questions in everyday wording (the 14 ministry-sheet questions of the test half) and not questions already close to the code's text. It is checked once at the final run, not tuned on.
- Seen in the rewrites: a rewrite can lose a detail (hw-08 "Pourquoi la période d'essai est-elle obligatoire dans un CDI ?" became "...est-elle obligatoire ...", the false premise question lost its "pourquoi"; the acronym ETTP was dropped in sheet-06). Largest losses: smoke-27 and mw-013 (-0.37 under fuse).
- Cost in production: one LLM call per user query, about 1 second in the pilot, 0.00005 USD per question.

## 2026-11-02: heading sentence pilot, local 4-bit model against DeepSeek, 50 articles (step 0c, in progress)
- Pilot only; no sentence is in a heading yet, nothing is embedded. Same 50 articles (seed 20261101: 40 Code du travail articles, 4 GDPR articles, 4 recitals, 2 annexes), one article per request, temperature 0. Prompts in `prompts/heading_sentence.yaml`: v1 restates the article in plain words, v2 asks for the question a worker or employer would ask, v3 adds first person, a question mark, a ban on invented persons and one invented example. Outputs in `docs/pilots/` (ids and sentences only).
- DeepSeek `deepseek-flash` (0.0046 to 0.0051 USD per 50 articles, about 1.2 USD for the corpus at the same rate, my extrapolation): v1 32.1 words, no question; v2 24.7 words, 50 of 50 questions, "patron" in 23 of 50 including GDPR articles that do not mention an employer; v3 21.6 words, 50 of 50 questions, "patron" in 0.
- Local `Qwen3.5-4B` Q4_K_M (bartowski GGUF) on the RTX 3060 Laptop, llama.cpp build b12034, server context 4,096 tokens per slot, longest prompt 3,182 tokens: one request alone 55 to 59 output tokens/s, 0.83 to 0.99 s per article, 42 to 50 s for 50 articles; four requests at once 26.5 tokens/s each, 25 s for 50 articles (about 0.5 s per article). The corpus would take roughly 1.6 hours (four slots) to 3 hours (one slot); the pilot sample has longer texts than the corpus average (1,029 against about 570 characters), so this is an order of magnitude. No thinking text; completion 39 tokens on average.
- Same input, same sentences on a rerun with one slot (0 of 50 differ); one slot against four slots: 26 of 50 sentences differ, so outputs depend on the server configuration and it must be recorded.
- Prompt following of the 4-bit model: with v2 only 14 or 15 of 50 outputs are questions (DeepSeek 50), many statements address the reader as "tu" or "ton"; with v1, 2 of 50 cite an article number. Both models invent content for the two annexes (one is a table of correspondences). The 8-bit model and prompt v3 on the laptop are the next measurement (`docs/handoff/local_llm_windows.md` section 13).

## 2026-11-02: heading sentence pilot, 8-bit model and prompt v3 (step 0c, in progress)
- Laptop round 2 (`docs/handoff/local_llm_windows.md` section 13), same 50 articles, `Qwen3.5-4B` Q4_K_M and Q8_0, prompts v2 and v3, outputs in `docs/pilots/`. The laptop's own report (GPU memory, file hashes) went to the user, not to the repository, so it is not recorded here. No 8-bit run with four slots exists: it ran out of CUDA memory on the 6 GB card (told by the user), so two slots is the most the 8-bit model can serve here.

| Run | Questions of 50 | "tu/ton" | Article number cited | "patron" | Wall s for 50 | Decode tokens/s per request |
|---|---|---|---|---|---|---|
| DeepSeek v3 | 50 | 0 | 0 | 0 | 8.8 | |
| 4-bit v2, one slot | 15 | 7 | 0 | 14 | 49.6 | 54.6 |
| 8-bit v2, one slot | 28 | 2 | 0 | 13 | 44.2 | 52.9 |
| 4-bit v3, one slot | 48 | 1 | 4 | 0 | 35.5 | 69.9 |
| 4-bit v3, four slots | 48 | 0 | 4 | 0 | 23.5 | 26.2 |
| 8-bit v3, one slot | 50 | 0 | 3 | 0 | 50.8 | 46.3 |
| 8-bit v3, two slots | 50 | 0 | 3 | 0 | 29.7 | 39.1 |

- The prompt is the lever, not the precision: v2 gives 15 (4-bit) and 28 (8-bit) questions of 50, v3 gives 48 and 50. Between 4-bit and 8-bit with v3, 44 of 50 sentences differ in wording; format and accuracy look alike.
- Content, read against DeepSeek v3 on 14 articles: both local models often answer another question than the article settles (a recital on groups of companies, one on data subject rights, the GDPR transfer article), act a role ("Je suis agent inspecteur du travail..."), make grammar slips ("Mon certification", "Si je détenez") and copy the article's own references to other texts ("l'article L. 262-28 du code de l'action sociale", "l'article 50-0 du code général des impôts", 3 or 4 of 50). DeepSeek v3 has none of these on the same 50.
- Output depends on the server setup: 4-bit one slot against four slots, 26 of 50 sentences differ; 8-bit one against two slots, 16 of 50.
- Time for the corpus at 0.47 s (4-bit, four slots) to 0.59 s (8-bit, two slots) per article: about 1.5 to 1.9 hours, from a sample with longer texts than the corpus average.
- Verdict against the rule set before the run (at least 48 questions, no "tu/ton", no invented persons, no cited article numbers): neither local model passes. The sentences will be written with DeepSeek (decision of the user, 2026-11-02, conditional on this quality result).

## 2026-11-02: heading sentences for the whole corpus, header-llm chunks (step 0c, in progress)
- Decision of the user (2026-11-02): option B, the sentence is added after the section titles ("Code du travail, article L1221-13. T1 > T2 > T3. <question>"); the sentences are written with DeepSeek because neither local model passed (entry above); the file may be published.
- `scripts/heading_sentences_all.py`, `deepseek-flash`, prompts `sentence.v3` (French) and `sentence.v3.en` (English GDPR; 12 English articles: 12 questions, no flag). 11,977 of 11,977 articles written, 0 failed, 26 minutes, 0.73 USD in the ledger (the first 200 articles cost 0.0156 USD). All 11,977 are questions, 21.6 words on average (longest 41); 14 cite an article number and are not used (the articles keep the plain heading), so 11,963 are used; "patron" in 40 of 11,524 French sentences, no "tu/ton". The 8 annexes got plausible questions.
- Published as the Release `heading-sentences-v3` (SHA-256 d77bf4c7...afb8, 2.9 MB).
- Chunks, variant `header-llm` (`variants.py`: the baseline settings plus `sentences`): 12,150 chunks against 12,136, 76 split articles against 69, none over the 1,024-token limit (longest 1,023), mean heading 339 characters against 206. Embedding on the laptop: `docs/handoff/header_llm_windows.md`. Not evaluated yet.

## 2026-11-02: LLM-written heading sentence, dev half (step 0c)
- Vectors: bge-m3, variant `header-llm` (12,150 chunks), embedded on the laptop (RTX 3060 Laptop, 113 s, peak 1,490 MB, same model revision as the baseline) from commit a80d28e with the sentences file of the Release `heading-sentences-v3`; Release `embeddings-bge-m3-header-llm-v1`, both SHA-256 equal to the notes, `sentences_sha256` in the run file equal to the file's. Loaded into the chunking run `header-llm`; `db-check` passes on the default run except the approximate-index recall check (84.9%), which does not touch the evaluation (exact scan); I did not check whether it changed since the extra vectors were added.
- Dense search, exact scan, same questions and settings, run `headerllm`:

| Run | nDCG@10 | Recall@10 | Recall@20 | Hit@5 | MRR@10 | nDCG@10 minus baseline [95% paired] |
|---|---|---|---|---|---|---|
| baseline (heading: section titles) | 0.738 | 0.893 | 0.926 | 0.902 | 0.670 | |
| header-llm (section titles + question) | 0.773 | 0.893 | 0.943 | 0.902 | 0.758 | +0.035 [-0.025, +0.097] |

- Verdict by decision 3b: not an improvement (nDCG@10 interval includes 0; Recall@10 unchanged). Other differences: MRR@10 +0.088 [+0.000, +0.180], Recall@20 +0.016 [-0.040, +0.076], Hit@5 +0.000. The first gold article is at rank 1 for 42 questions against 39; 17 questions improve, 13 get worse, 31 are unchanged.
- By who wrote the question (mean nDCG@10 change; per-question bootstrap, not the cluster bootstrap of `compare`, so only indicative): model-written +0.052 (30 questions, the same model family as the sentences), ministry sheets +0.031 (15), smoke +0.031 (12), hand-written -0.059 (4). The 31 questions that do not share the sentence writer's family move by about +0.02 on average. The gain is concentrated where the questions and the sentences come from the same family, which is what the same-family bias would produce; this does not prove it.
- Groups against the baseline: E +0.207 (5 questions), H +0.168 (3), B +0.068 (15), A +0.022, I +0.031; D -0.286 (1), G -0.281 (3), C -0.061 (2); all inside the noise.
- Cost: 0.73 USD for the sentences, 113 s of GPU for the vectors; search time unchanged (0.455 s per question including the db round trip).
- Decision: the baseline heading stays; `header-llm` is a measured option. Left open for the user: use it in the final setup on the strength of the MRR hint, or keep it only as a pre-registered comparison on the test half.

## 2026-11-02: do the sentences help keyword search? header-llm with BM25 and fusion, dev half (step 0c)
- Same keyword search (BM25 on the lexemes of `chunks.tsv`, which now contain the question) and the same fusion with dense (k 60, top 100 each, keyword weight 1, 0.5, 0.25), run on the chunking run `header-llm`; runs `llm-keyword`, `llm-hybrid-w10`, `llm-hybrid-w05`, `llm-hybrid-w025`. Compared with the same method on the plain heading, and with the dense baseline (rule 3b).

| Search | plain heading nDCG@10 | header-llm nDCG@10 | header-llm minus plain heading [95% paired] | MRR@10 change | header-llm minus dense baseline |
|---|---|---|---|---|---|
| dense | 0.738 | 0.773 | +0.035 [-0.025, +0.097] | +0.088 [+0.000, +0.180] | |
| keyword alone | 0.548 | 0.677 | +0.129 [+0.054, +0.210] | +0.150 [+0.067, +0.242] | -0.061 [-0.154, +0.026], Recall@10 -0.128 [-0.218, -0.037] |
| hybrid, weight 1 | 0.701 | 0.785 | +0.085 [+0.035, +0.145] | +0.123 [+0.063, +0.197] | +0.048 [-0.031, +0.118] |
| hybrid, weight 0.5 | 0.716 | 0.773 | +0.057 [+0.005, +0.118] | +0.107 [+0.045, +0.183] | |
| hybrid, weight 0.25 | 0.749 | 0.786 | +0.037 [-0.019, +0.100] | +0.102 [+0.026, +0.183] | +0.048 [-0.016, +0.112], MRR@10 +0.111 [+0.017, +0.203], Recall@10 -0.008 |

- The sentences help keyword search clearly: the question puts everyday words into the text the keyword search reads (nDCG@10 +0.13 alone, +0.09 to +0.04 fused; MRR@10 +0.10 to +0.15 in every row). Keyword alone stays worse than dense (Recall@10 clearly down).
- They do not make fusion better than dense on the same chunks: hybrid minus dense header-llm is +0.013 [-0.023, +0.047] (weight 0.25), +0.013 [-0.060, +0.083] (weight 1), +0.000 [-0.050, +0.053] (weight 0.5). The fused runs are not improvements over the dense baseline by 3b (nDCG@10 intervals include 0); their gain over the baseline is the dense effect of the sentence.
- Questions not written by the sentence's model family (31): mean nDCG@10 change against the baseline +0.019 dense, +0.038 hybrid weight 0.25, +0.024 hybrid weight 1; model-written (30): +0.052, +0.058, +0.072. The same-family bias applies to keyword matching as well (shared wording).
- Counting: this adds eight comparisons to the many already made on one 61-question half; the within-method gains for keyword and weight 1 and 0.5 clear zero, the rest does not.
- Decision of the user (2026-11-02): the heading with the LLM-written question stays a measured option and is not part of the final setup; the final setup keeps the baseline heading. It may be raised again if keyword search becomes part of the retrieval.

## 2026-11-02: Postgres ts_rank as the word-matching search, dev half (step 0c)
- Same protocol as the BM25 entry of 2026-10-29: the question's lexemes (same French/English text-search configuration as the chunks) joined by OR and matched against `chunks.tsv`; chunks ordered by `ts_rank(tsv, query, flag)`, best chunk per article, top 400 chunks; alone and fused with dense by reciprocal rank fusion (k 60, top 100 each, keyword weight 1, 0.5, 0.25). `--lexical tsrank` is ts_rank with its defaults (flag 0, no length normalisation); `--lexical tsrank-len` divides by 1 + log(length) (flag 1). Default chunking, baseline heading, runs `tsrank-*` and `tsranklen-*`.

| Search | nDCG@10 | Recall@10 | MRR@10 | nDCG@10 minus dense baseline [95% paired] | minus BM25, same weight |
|---|---|---|---|---|---|
| dense baseline | 0.738 | 0.893 | 0.670 | | |
| BM25 alone | 0.548 | 0.697 | 0.505 | -0.190 | |
| ts_rank alone | 0.426 | 0.600 | 0.383 | -0.312 [-0.427, -0.204], Recall@10 -0.294 | -0.122 [-0.203, -0.044] |
| ts_rank-len alone | 0.491 | 0.637 | 0.460 | -0.246 [-0.360, -0.142], Recall@10 -0.256 | -0.056 [-0.105, -0.009] |
| ts_rank fused, weight 1 / 0.5 / 0.25 | 0.674 / 0.714 / 0.735 | 0.826 / 0.891 / 0.891 | 0.615 / 0.649 / 0.681 | -0.064 / -0.024 / -0.003 | weight 0.25: -0.014 [-0.058, +0.034] |
| ts_rank-len fused, weight 1 / 0.5 / 0.25 | 0.682 / 0.694 / 0.704 | 0.842 / 0.861 / 0.861 | 0.626 / 0.621 / 0.624 | -0.055 / -0.044 / -0.033 | weight 0.25: -0.045 [-0.083, -0.008] |

- Verdict by decision 3b: no setting is an improvement; every nDCG@10 interval against the dense baseline includes 0 or lies below it, and the two ts_rank searches alone are clearly worse than BM25. As expected, ts_rank does not weigh rare words more (no inverse document frequency), which BM25 does. Dense stays the retrieval default.

## 2026-11-02: bge-m3 sparse as the word-matching search, dev half (step 0c)
- Vectors: bge-m3 sparse (the model's own word-weight head, `relu(linear(last hidden state))`, highest weight per token id, special tokens dropped; score = sum of weight products over shared tokens), default chunking, 12,136 chunks, encoded on the laptop (RTX 3060 Laptop, 105 s, peak 1,491 MB, 71.7 tokens per chunk on average, same model revision as the dense baseline) from commit 73137c2; Release `embeddings-bge-m3-sparse-v1`, both SHA-256 equal to the notes. The index checks the file against the `default` run: the same 12,136 chunks and the hash of every chunk text.
- Same protocol as BM25 and ts_rank: alone, and fused with dense by reciprocal rank fusion (k 60, top 100 each, keyword weight 1, 0.5, 0.25); runs `sparse-keyword`, `sparse-hybrid-w10`, `sparse-hybrid-w05`, `sparse-hybrid-w025`.

| Search | nDCG@10 | Recall@10 | MRR@10 | minus dense baseline [95% paired] | minus BM25, same weight |
|---|---|---|---|---|---|
| dense baseline | 0.738 | 0.893 | 0.670 | | |
| BM25 alone | 0.548 | 0.697 | 0.505 | -0.190 | |
| sparse alone | 0.639 | 0.775 | 0.587 | -0.099 [-0.184, -0.009], Recall@10 -0.119 [-0.204, -0.036] | +0.091 [+0.004, +0.195] |
| sparse fused, weight 1 | 0.732 | 0.851 | 0.680 | -0.006 [-0.066, +0.049] | +0.032 [-0.029, +0.103] |
| sparse fused, weight 0.5 | 0.762 | 0.865 | 0.714 | +0.024 [-0.026, +0.071] | +0.046 [-0.007, +0.106] |
| sparse fused, weight 0.25 | 0.767 | 0.885 | 0.711 | +0.029 [-0.008, +0.066] | +0.018 [-0.028, +0.069] |

- Verdict by decision 3b: no setting is an improvement (every nDCG@10 interval against the dense baseline includes 0, alone it is clearly lower). Sparse is clearly better than BM25 alone (+0.091 [+0.004, +0.195]) and its fusions are better than BM25's in point estimate, but not distinguishable from them; the learned weights help a keyword search, they do not make it beat dense.
- Rule of the test plan (`0004`, written 2026-11-02 before this run): sparse goes on the test half only if one setting reaches nDCG@10 +0.03 over the dense baseline. The best is weight 0.25 with +0.02915, so the rule is not met and **sparse is not run on the test half**.
- Multiple comparisons: this adds four comparisons to those already made on one 61-question dev half.

## 2026-11-02: final test session, test half (step 0c)
- The test half was opened once, with `--final`, at the clean commit dc7924c, following the plan written before (`docs/decisions/0004-step-0c-decisions.md`, "Final test plan"). 65 questions (63 French, 2 English); 64 have gold (59 answerable, 3 false premise, 2 underspecified), 1 unanswerable; 43 clusters. Runs `final-*`. The rewrites of the test questions were made once with `rewrite.v1` (0.0066 USD; 52 of 65 searched with a changed rewrite, none flagged). bge-m3 sparse was not run: its best dev setting (+0.02915) did not reach the threshold of the plan.
- **Final setup (the baseline)**, test half: nDCG@10 0.746 [0.649, 0.828], Recall@10 0.865 [0.772, 0.942], Recall@5 0.792 [0.689, 0.882], Recall@20 0.880 [0.791, 0.957], Hit@5 0.828 [0.726, 0.914], MRR@10 0.693 [0.589, 0.788], nDCG@5 0.720 [0.616, 0.808]. The dev half gave nDCG@10 0.738.
- Secondary comparisons against it (paired differences, intervals not adjusted for the number of comparisons):

| Run | nDCG@10 | Recall@10 | Hit@5 | MRR@10 | nDCG@10 minus final setup [95% paired] | Recall@10 minus final setup | Verdict by 3b |
|---|---|---|---|---|---|---|---|
| Qwen3-Reranker, top 50 | 0.765 | 0.896 | 0.828 | 0.710 | +0.019 [-0.063, +0.101] | +0.031 [-0.006, +0.082] | not an improvement |
| Rewrite fused with the original | 0.766 | 0.880 | 0.844 | 0.714 | +0.021 [+0.005, +0.041] | +0.016 [+0.000, +0.053] | improvement (nominal) |
| header-llm heading | 0.781 | 0.927 | 0.891 | 0.709 | +0.036 [-0.017, +0.094] | +0.062 [+0.014, +0.130] | not an improvement |
| Article-number rule | 0.746 | 0.865 | 0.828 | 0.693 | 0.000 | 0.000 | no effect |

- Rewriting: 8 questions up, 1 down (hw-06, -0.069), 55 unchanged. The hypothesis of 2026-11-02 (it helps the 14 ministry-sheet questions) is not supported: none of the 14 changed. The gain is on model-written questions (+0.028, 6 up, 0 down), smoke (+0.024) and hand-written (+0.022). Four questions carry most of the average (smoke-06 +0.36, mw-048 +0.34, mw-088 +0.28, hw-12 +0.20). Dev was +0.010 [-0.022, +0.045].
- Reranker: the dev pass (+0.061 [+0.003, +0.125]) does not repeat: test +0.019 [-0.063, +0.101]; 15 questions up, 14 down, 35 unchanged. By who wrote the question (mean nDCG@10 change): model-written +0.131 [+0.029, +0.260] (29), ministry sheets -0.053 (14), smoke -0.079 (15), hand-written -0.105 (6). 89.9 s per question on this CPU (the Mac was swapping; same order as on dev), `truncated_pairs` 0.
- header-llm: nDCG@10 +0.036 repeats the dev figure (+0.035) with an interval that still includes 0; Recall@10 is clearly up on test (+0.062 [+0.014, +0.130]) and was unchanged on dev. 16 questions up, 9 down, 39 unchanged. By provenance: smoke +0.107 (15), model-written +0.051 (29), ministry sheets -0.016 (14), hand-written -0.096 (6).
- Article-number rule: no test question names an article by number, so no ranking changed; the rule has been exercised on one dev question only.
- Counting: four comparisons were run; the chance that at least one passes at 5% by luck is about 19% (1 - 0.95^4). Per the plan these comparisons never change the setup: the final setup stays the dense baseline. The nominal pass of rewriting and the Recall@10 gain of header-llm are for the user to weigh at the review gate.
- Costs of the stage: the DeepSeek ledger holds 2.55 USD in total (question writing and review 1.78, heading sentences 0.75, pilots and rewrites about 0.02); the laptop did the vectors in about 15 minutes of GPU time in total.

## 2026-11-09: validating the claim judge against hand labels (step 0d)
- Change: `src/legalrag/claimjudge.py`, `scripts/judge_claims.py`, `prompts/judge.yaml` (`judge.v1`, `judge.v2`), `src/legalrag/labelsheet.py` and `scripts/make_label_sheet.py` (the labelling sheets), `eval/answer_checks.json` (23 claim checks: 19 real claims edited in one controlled way, 4 unchanged).
- Labels: the labeller (user) labelled 29 answers of the `answer.v3` pilot in two sheets, 49 claims in all; the 8 clearest edits first labelled "supported" and the refusals hw-11 and sheet-13 were corrected after the labeller re-read the texts, and mw-035 claim 0 after the rule "the passage says it, whatever the question" was restated; every correction is in `data/labels/answers.labels.json` with the original label.
- Result, agreement with the labels, kappa, errors caught (human: partly or not supported, 17), good claims flagged (human: supported, 31 or 32): v4-pro v1 67%, 0.48, 16, 13 and thinking 60%, 0.44, 17, 18; v4-pro v2 76%, 0.57, 16, 9 and thinking 68%, 0.51, 17, 14 (2 empty replies); flash v2 82%, 0.68, 17, 8 and thinking 69%, 0.51, 16, 13; a Claude helper agent from the session (v1 rule text, no labels seen, 48 claims) 88%, 0.76, 16, 4. Bootstrap 95% intervals of kappa (48 claims): flash 0.49 to 0.84, v4-pro 0.37 to 0.74, Claude 0.58 to 0.92.
- Costs: 0.004 to 0.095 USD per run of about 49 claims (flash no thinking 0.004; v4-pro thinking 0.095).
- Limits: the v2 prompt was written after reading the v1 disagreements; 49 claims, 17 of them errors; the answer model and the judge are the same model. Decision 16 of `docs/decisions/0006-step-0d-decisions.md`.

## 2026-11-10: answer metrics of the `answer.v3` pilot, dev half (step 0d)
- Change: `src/legalrag/answermetrics.py`, `scripts/answer_metrics.py` (decision 17 of 0006), the judge calls moved to `claimjudge.run_judge`. Run: `answer_metrics.py --tag flash-v3` (answers of `deepseek-flash`, prompt `answer.v3`, threshold 0.55, 65 dev questions; judge `deepseek-flash`, `judge.v2`, no thinking; output `data/pilot/metrics_flash-v3.json`).
- Faithfulness, 206 claims of 57 answers: 175 supported (85%), 26 partly (13%), 5 not supported (2.4%); 30 of 57 answers have every claim supported, 5 answers have a claim marked not supported; 0 judge errors. On the hand-labelled set the judge flagged 8 of 32 good claims, so the supported share is a lower bound.
- The 5 claims marked not supported (read, not hand-labelled): mw-016 claim 2 ("doit aussi" made of a condition), mw-074 claim 2 ("peut être retirée" for "est retirée") and sheet-22 claim 3 (a "depends" line naming département and commune) look like real drift; hw-07 claim 0 and smoke-21 claim 0 are debatable.
- Citations, 55 answered answerable questions: 51 cite a gold article, 49 a primary gold one; 62 of 95 cited articles are gold (65%, a lower bound on precision).
- Refusals: 58 answerable, 55 answered, 3 refused and all 3 are retrieval misses (no gold article in the top 5), 0 refused with the evidence shown; 5 of 6 unanswerable or false-premise questions refused (the one answered, hw-07, corrects the false premise); the underspecified question was answered.
- Cost: answers 0.0235 USD (64 calls, 140,644 tokens in, 10,649 out, median 1.65 s); judge 0.016 USD (206 calls). The DeepSeek ledger holds 2.97 USD in total.

## 2026-11-10: LlamaIndex CitationQueryEngine against our answer path, dev half (step 0d, decision 5 of 0006)
- Change: `scripts/citation_pilot.py`, `src/legalrag/citationcompare.py`. The engine (llama-index-core 0.14.25, default prompt, 512-token source chunks, `deepseek-flash`, temperature 0, thinking off) gets our retriever's nodes (top 5 articles) behind the same weak-retrieval check (0.55), so only the answering differs. Its text with `[n]` or `[Source n]` marks is converted into our rows (one claim per cited sentence; sentences with no valid mark are dropped as our resolver drops them) and scored by the same judge (`deepseek-flash`, `judge.v2`) and `answermetrics`. A first run read only `[n]` and counted 12 answers as refusals because the model wrote `[Source n]`; fixed and rerun.
- Our path (`answer.v3`) against the engine, 65 dev questions: claims judged 206 against 126; supported 175 (85%) against 108 (86%); not supported 5 (2.4%) against 3 (2.4%); answers with every claim supported 30 of 57 against 49 of 64 (the engine writes 2.0 claims per answer, ours 3.6, and its passages are longer); answerable questions answered 55 of 58 against 58 of 58; answers citing a gold article 51 of 55 against 52 of 58; cited articles that are gold 62 of 95 against 66 of 102; passage shown per claim, mean 311 characters (median 274) against 920 (median 699); tokens in 140,644 against 157,360, out 10,649 against 9,635; median model time 1.65 s against 1.60 s; cost 0.0235 USD against 0.0276 USD on the first, cold-cache run (0.0081 USD on the rerun, which hit DeepSeek's cache).
- Refusals: the engine has no refusal signal, only words. Unanswerable and false-premise questions refused by the weak-retrieval check 1 of 6 (ours 5 of 6); 5 answers say in words that the sources do not cover the question (hw-09, hw-10, smoke-29, and the answerable mw-074 and sheet-13) yet cite sources, so they count as answered; 24 sentences in 19 answers carry no citation.
- Limits: one run per engine; the judge was validated on our short passages, and the longer passages of the engine make support easier to find; the judge is the answer model.

## 2026-11-10: the claim judge on the expert labels of ClaimRAG-LAW, English GDPR (step 0d)
- Data: https://huggingface.co/datasets/SNTSVV/ClaimRAG-LAW (CC BY 4.0, research use; paper arXiv 2605.21071), files GDPR-RAG-LAW.json (149 questions, reference answers, source chunks) and GDPR-CLAIM-LAW.json (68 questions, 520 claims as triples with the expert's entailment label against the source chunk), kept in `data/claimrag/`, not committed. Code: `src/legalrag/claimrag.py`, `scripts/claimrag_judge.py`, `prompts/claim_rewrite.yaml`.
- Findings on the data: the English text is the same as ours (5-word overlap 93% to 100% for single-article chunks) but their chunks are fixed-size slices that often span 2 or 3 articles; the 149 questions use 39 distinct chunks, about 15 articles (31 questions on article 49 alone); 22 of the 450 usable claims have an empty chunk and are left out; labels: Entailment 292, Neutral 151, Contradiction 7 (9 "does not make sense" and 61 unlabelled left out).
- Triples to sentences: the plain template ("subject relation object.") against a model rewrite (`deepseek-flash`, `claim.rewrite.v1`, which copied the template in 310 of 450 cases). Judge `deepseek-flash`, `judge.v2`, no thinking, the source chunk as the passage, two classes (Entailment against the rest). Template: agreement 64%, kappa 0.32, Neutral or Contradiction caught 133 of 157, Entailment flagged 130 of 271 (428 claims). Rewrite: 64%, kappa 0.33, 133 of 157, 129 of 271. No gain from the rewrite, so the template is kept and no model step is added.
- Reading: the judge, which says "supported" only when the passage states the claim, flags about half of the claims the expert called Entailment (the expert accepts what a reader would infer, and many claims are short fragments such as "GDPR has primary objectives"), and catches 85% of the Neutral and Contradiction claims. Kappa 0.32 here against 0.68 on our own labels: the outside labels use a looser notion of entailment than the judge's rule, so they do not validate the judge as defined.
- Cost: 0.082 USD (rewrites 0.009, judge runs 0.042 and 0.031; the chunks are long, so more than the 3 cents estimated).

## 2026-11-10: a looser judge prompt for completeness, `judge.v3`, on the ClaimRAG-LAW expert labels (step 0d)
- Change: `prompts/judge.yaml` `judge.v3` ("a careful reader of the passage would conclude the claim": paraphrase, summary and plain inference count; numbers, units, negations, may or must, who and only still checked), `scripts/claimrag_judge.py` with `--half`, `claimrag.half` (even or odd query id, so one question stays in one half). For completeness only, not faithfulness (`judge.v2` stays the faithfulness judge, decision 16).
- Protocol: one draft of `judge.v3`, run on the dev half (218 claims) beside `judge.v2`, no change after that, then one run of each on the test half (210 claims). Judge `deepseek-flash`, no thinking, template sentences, two classes.
- Dev half: v2 agreement 62%, kappa 0.30, Neutral or Contradiction caught 62 of 71, Entailment flagged 74 of 147; v3 71%, kappa 0.41, 56 of 71, 49 of 147.
- Test half: v2 68%, kappa 0.39, caught 74 of 86, Entailment flagged 55 of 124; v3 72%, kappa 0.44, 65 of 86, 37 of 124. The gain holds on the held-out half: fewer good claims flagged, at the cost of catching fewer of the expert's Neutral and Contradiction claims.
- Data caveat found on the way: the claim file and the RAG file of ClaimRAG-LAW use the same query ids for different questions in 39 of 68 cases (the question text is equal in only 29), and the claim file's chunk is a much shorter piece than the RAG file's chunk (median 8% of its length). The expert's labels may refer to a context other than the chunk we show the judge, so kappa here is a weak benchmark.
- Cost: 0.064 USD for the four runs.

## 2026-11-10: which chunk did the ClaimRAG-LAW experts label against? (step 0d)
- Question: the claim file and the RAG file give a different `relevant_chunk` for the same question (claim file: a short piece, median 8% of the length; ids name the same question in only 29 of 68 cases). Test: `judge.v3` on the 123 claims of the questions both files share (14 more have an empty claim-file chunk), once with the claim file's chunk and once with the RAG file's longer chunk (`scripts/claimrag_judge.py --matching-only` and `--chunk rag-file`).
- Result on the same 123 claims: claim-file chunk agreement 70%, kappa 0.33, Neutral or Contradiction caught 23 of 37, Entailment flagged 23 of 86; RAG-file chunk 63%, kappa 0.00, caught 7 of 37, Entailment flagged 16 of 86. With the longer text almost every claim becomes inferable, including most of the expert's Neutral claims.
- Reading: the expert's labels are relative to the claim file's own short chunk, as the file pairs them. The check already used that pairing, so the earlier worry that the labels referred to a longer context is not supported. The low kappa comes from the looseness of the expert's Entailment on fragment claims and from the 13% of claims the expert marked incorrect.
- Cost: about 0.01 USD.
