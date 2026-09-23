# Development without a hosted database

Bangladesh Industrial Intelligence does not require Supabase during the validation and data-engineering phase.

## Current storage pattern

- GitHub: public code, schemas, tests and methodology only.
- Local/private SQLite: validation metadata, entity links and working observations.
- Local/private Parquet: larger analytical extracts where columnar storage is useful.
- Local/private raw snapshots: source HTML/JSON retained outside GitHub with hashes recorded in the database.

This is sufficient for candidate discovery, the 2,000-establishment validation, parser development, entity matching, enrichment coverage analysis, repeat-refresh testing and the first national extraction.

## When a hosted database becomes useful

Move to hosted PostgreSQL when the project needs persistent remote API access, concurrent users, authentication, production scheduling, customer-facing search/filtering, or geospatial queries exposed to an application.

The schema is intentionally portable PostgreSQL. Supabase is one deployment option, not a dependency. Alternatives can include other managed PostgreSQL services; application-facing deployments may also use Cloudflare services where appropriate.

## Portability rule

Source collection, parsing, matching and validation logic must not import a vendor-specific database SDK. Database access belongs behind a storage boundary so the commercial data asset can move between providers without rewriting the intelligence engine.
