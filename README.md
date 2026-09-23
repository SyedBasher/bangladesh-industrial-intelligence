# Bangladesh Industrial Intelligence

Refreshable industrial-establishment intelligence for Bangladesh, using the public DIFE/LIMA establishment register as the backbone and keeping source provenance explicit.

## Repository policy

This is the **public software and methodology repository**. It intentionally does **not** contain the commercial/working database, raw source archives, API keys, private exports, or customer data.

The private data layer is designed to live outside GitHub. During validation we can use local SQLite/Parquet; when a live backend is needed, the preferred analytical store is PostgreSQL/PostGIS (for example Supabase or another managed Postgres service).

## Current architecture

- DIFE/LIMA remains the establishment/site backbone.
- Organization and establishment/site are separate entities.
- Source snapshots and record versions are immutable.
- Official source fields never get overwritten by calculated/enriched fields.
- External enrichment is designed for EPB, BGMEA, BKMEA, BEPZA and Department of Environment records.
- Entity resolution distinguishes `EXACT_SITE`, `PROBABLE_SITE`, `ORGANIZATION_ONLY`, `AMBIGUOUS`, `NO_MATCH`, and `SOURCE_FEASIBILITY_ONLY`.
- Live bulk collection remains gated until current automation/reuse conditions are verified.

## Development sequence

1. Feasibility audit — completed.
2. 300-row DIFE pilot — completed.
3. Organization/site and provenance architecture — completed.
4. Collector/versioning design — completed.
5. 2,000-record validation design — completed.
6. External enrichment design — completed.
7. Public-code baseline and CI — this repository.
8. 2,000-record live validation — next empirical gate once collection conditions are verified.

## Layout

```text
src/bii/                  core reusable Python logic
database/migrations/      PostgreSQL schema migrations
tests/                    synthetic parser/matching tests
docs/                     methodology, source and validation rules
.github/workflows/        public CI only; no private data
```

## Local development

```bash
python -m pip install -e .[dev]
pytest -q
```

## Data rule

Do not commit real DIFE/EPB/BGMEA/BKMEA/BEPZA/DoE extracts to this repository. Keep raw and derived datasets outside GitHub and retain exact source URLs, retrieval times, source vintages and content hashes in the private data layer.
