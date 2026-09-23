# Changelog

## v0.14.0-dev — 2026-09-23

- Added scalable local name-block indexing for staged external source records.
- Added five explicit shortlist priority classes; shortlist ranking is separate from final matching.
- Added append-only external candidate runs, record-level candidate evidence and resolution outcomes.
- Added conservative automatic resolution: unique site/org positives may be selected; multiple plausible positives remain ambiguous.
- Added two-phase application so candidate generation never writes entity links until auto-resolutions are explicitly applied.
- Preserved NO_STAGED_CANDIDATE as a non-negative state.
- Added PostgreSQL migration parity for candidate search and resolution.

## v0.13.0-dev — 2026-09-23

- Added staged parsers and stable-key rules for EPB, BGMEA, BKMEA, BEPZA and DoE.
- Added source-specific sector eligibility and linkage-scope rules.
- Added transparent site-vs-organization evidence generation with no opaque confidence score.
- Added private external record/version storage, enrichment targets, entity links and match-evidence audit records.
- Added source-level coverage reports and explicit protection against absence-based negative inference.
- Added PostgreSQL migration parity for the enrichment validation layer.

## v0.12.0-dev — 2026-09-23

- Added list-to-detail anomaly detection for district, status, sector, class and name variation.
- Added versioned validation reports with sector and geography breakdowns.
- Added automatic progressive detail validation: 100 → 500 → 2,000 without manual pauses when each QC gate passes.
- The controller stops at the first failed gate and never overrides locked checkpoints.
- Added PostgreSQL migration parity for validation reports and anomaly records.

## v0.11.0-dev — 2026-09-23

- Added an explicit source-access policy gate; public visibility alone cannot enable live collection.
- Added a single-threaded HTTPS-only collector with host/path allowlists, rate limiting, bounded retries, Retry-After handling and response-size limits.
- Added the private READY-checkpoint detail runner.
- Added private database audit records for access-policy reviews and collection runs.
- Added PostgreSQL migration parity for collection audit structures.
- Kept the DIFE policy template at UNKNOWN pending a documented automation/reuse review.

## v0.4.0-dev — 2026-09-23

- Established the public GitHub code/methodology baseline.
- Added a strict `.gitignore` separating public code from private data.
- Added a PostgreSQL `bii` schema migration for the core provenance/entity model.
- Added conservative DIFE public-list parsing that only accepts IDs exposed in public detail links.
- Added transparent site-vs-organization match classification.
- Added synthetic regression fixtures and CI.
- Retained the 2,000-record validation and external-enrichment methodology documents.
- No real DIFE or external-source extracts are committed.

## v0.3.0 — 2026-09-23

- Completed the external-enrichment architecture for EPB, BGMEA, BKMEA, BEPZA and DoE.
- Defined immutable external record versioning and match-evidence rules.
- Defined stable external-key conventions and source-specific interpretation rules.
- National/live bulk collection remains gated pending automation/reuse verification.
