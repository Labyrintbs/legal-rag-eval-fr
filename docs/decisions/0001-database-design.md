# Database design: why it is built this way

Written 2026-10-22. Measured numbers are in `EXPERIMENT.md`; the schema is `migrations/versions/0001_initial_schema.py`.

## Principles
1. **Plain Postgres + pgvector, nothing cloud-only.** The same database runs on the laptop, the VPS and AWS. Data and code stay portable.
2. **Everything can be rebuilt.** Raw files are fetched and checksummed, chunks are derived by code, vectors are derived by a model. The database holds derived data; losing it costs a rebuild, not information.
3. **One thing per table.** What the source says (`articles`), how we cut it (`chunks`), and what a model made of it (`chunk_embeddings`) change for different reasons, so they are separate. A second model adds rows, not columns. A second chunking adds a `chunking_runs` row and its chunks.
4. **Never silently mix.** A chunking run cannot change once stored; a vector is refused if the text it was computed from differs (hash check); a vectors file must cover exactly the chunks of the run. Loads run in one transaction.
5. **Loading is safe to repeat.** Articles are upserted, chunks are added only when missing, vectors are replaced in place.
6. **Search methods are separate columns and indexes**, so any of them can be replaced by a new migration without touching the others: exact filters (ordinary columns), keyword search (`chunks.tsv` + GIN), meaning search (`chunk_embeddings.embedding` + HNSW).
7. **Settings come from the environment** (`DATABASE_URL`); the structure is changed only by numbered migrations (Alembic), so every machine gets the same change.

## Tables
`corpus_versions` (which source file, which checksum, which licence) -> `articles` (one per article or recital) -> `chunks` (one per piece of text, belongs to a `chunking_runs` row) -> `chunk_embeddings` (one vector per chunk and model).

## Indexes
- **GIN on `tsv`:** word root -> list of chunks; keeps keyword search from reading every chunk.
- **HNSW on the vectors, cosine, partial per model:** a prebuilt network of shortcuts between vectors. Partial because vectors of different models cannot be compared, so each model gets its own index; queries must name the model.
- Both are built after the bulk load (cheaper than updating them row by row).

## What the measurements say (synthetic copies, see `EXPERIMENT.md`)
- Exact vector search grows with the data: 40 ms at 12,000 vectors, 547 ms at 97,000. HNSW stays at 2 to 4 ms with recall of 0.998 or more. The index is worth having already at our size.
- The HNSW index costs about 7.8 KB per vector and about 0.8 s to build per 1,000 vectors; it should fit in memory. At 1,000,000 vectors that is roughly 8 GB (straight extrapolation, not measured).
- Insert into a loaded table is dominated by HNSW (about 5 ms per row against 0.25 ms without it). Delete is fast but only marks rows dead; space is reclaimed by VACUUM and files do not shrink. Our data changes in batches, so we load, then index.
- Keyword ranking cost follows the number of matching chunks, so very common words get slower as the corpus grows.

## Known limits and open points
- Keyword search uses Postgres's French stemmer, which maps "démission" and "démissions" to different roots. Whether to keep it is a step 0c decision.
- The keyword column is built from header and body together (a word in a section title matches every chunk of that section). To be tested in 0c.
- Migration `0002` (2026-10-26) limits `lang` to fr/en and `kind` to article/recital/annex, and makes deleting a chunking run delete its chunks and their vectors (`legalrag delete-run`, which asks first). Articles are shared by runs and stay.
- `valid_to` keeps the source value: Code du travail uses 2999-01-01 for "no end date", GDPR rows use NULL. Decide when the first query filters on dates (step 0c).
- The database tests skip when no Postgres is reachable; the CI of step 0e must start one.
- When comparing query plans from Python, disable prepared statements (`prepare_threshold=None`); otherwise a cached plan makes the comparison meaningless (this happened once, see `EXPERIMENT.md`).
