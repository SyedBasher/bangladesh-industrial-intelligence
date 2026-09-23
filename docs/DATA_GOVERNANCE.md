# Data governance

## Public repository boundary

GitHub contains software, schemas, tests, methodology and deliberately tiny synthetic fixtures only.

The following stay outside GitHub:

- real source extracts or page archives;
- SQLite/PostgreSQL database dumps;
- CSV/Parquet/XLSX exports;
- API keys and credentials;
- customer or user information;
- unpublished commercial outputs.

## Provenance rule

Every source observation should retain the source authority, exact URL, retrieval timestamp, source-provided vintage/update time when available, parser version and content hash.

## Official vs calculated fields

Source-provided values remain source-native. Derived fields are stored separately and labelled with their method/version. Missing values are never imputed merely to improve coverage.

## Entity resolution rule

Organization-level evidence must not be copied automatically to individual plants. Site-level enrichment requires site-level evidence.
