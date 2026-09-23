# Changelog

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
