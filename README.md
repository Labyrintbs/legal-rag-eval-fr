# legal-rag-eval-fr

Question answering over French labour law (Code du travail) and the GDPR, with measured evaluation. French questions first. Answers cite articles and refuse when the corpus cannot answer.

**Status:** step 0a (ingest) in progress. Nothing is deployed.

**Disclaimer:** legal information, not legal advice.

## Corpus

- Code du travail: community extract `VinceGx33/legi-french-law-2025`, built on the official DILA/LEGI dump of 2025-07-13. In-force articles only, so answers reflect the law as of that date.
- GDPR (Regulation (EU) 2016/679): text from the EU Publications Office, French and English.

Attribution: see [NOTICE.md](NOTICE.md).

## Setup

```
uv sync
make fetch     # raw data into data/raw/ (gitignored), checksums verified
make db-up
```

Needs Docker and [uv](https://docs.astral.sh/uv/).

## Tracking

- [EXPERIMENT.md](EXPERIMENT.md): every change to data processing and chunking, with its measured effect.
- `docs/decisions/`: short notes on design decisions.
- `docs/data_profiles/`: statistics of each source.
