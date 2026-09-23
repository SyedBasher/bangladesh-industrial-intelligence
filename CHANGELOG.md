# Changelog

## v0.25.0-dev — 2026-09-24

- Added a BBS-backed administrative geography crosswalk for division, district and upazila names/codes.
- Added exact English/Bangla canonical matching plus explicit source-specific aliases; no fuzzy geography matching.
- Added canonical BBS composite geography references for cross-source joins.
- Added the first real exposure-source adapter for the DDM AWARE district Risk Information table.
- Preserved DDM Hazard Exposure, Vulnerability, Lack of Coping Capacity, Risk and Climate Zone as published text; no 1–5 conversion or proprietary risk score.
- Added a DISASTER_RISK exposure domain and canonical geography metadata on exposure observations.
- Added staged DDM import auditing with unresolved-geography reporting.
- Added PostgreSQL migration parity and end-to-end tests joining English DDM geography to Bangla DIFE geography through BBS.
- No full BBS geography extract or real DDM dataset is committed.

## v0.24.0-dev — 2026-09-24

- Added scope-aware first-order spatial exposure observations for climate hazards, transport access, power-system context and environmental/regulatory evidence.
- Added explicit SITE, UPAZILA and DISTRICT scopes with SITE_SPECIFIC, UPAZILA_CONTEXT and DISTRICT_CONTEXT attribution.
- Added exact-only geographic matching in v1; no fuzzy place-name inference.
- Added evidence-coverage calculations that explicitly do not represent risk prevalence.
- Added establishment, district and sector exposure profiles using establishment-count weighting only.
- Added private exposure-source provenance and safe product APIs that exclude private references and internal IDs.
- Added PostgreSQL migration parity, product schemas and methodology documentation.
- No real exposure dataset or second-order supply-chain propagation is committed.

## v0.23.0-dev — 2026-09-23

- Added safe national District Profiles and Sector Profiles derived only from approved national product contracts.
- Added district upazila/status/source-sector/sector-family composition and transparent location-quotient specialization flags.
- Added sector district distribution, HHI, largest-three/five district shares and source-label composition.
- Added exact registry versus external-enrichment coverage distinctions.
- Added registry drill-down filters and safe profile JSON export.
- Added district/sector profile JSON Schemas and methodology documentation.
- No real national DIFE snapshot is committed.

## v0.22.0-dev — 2026-09-23

- Added policy-independent ingestion of fixed private DIFE HTML archives with manifest/hash validation.
- Added normalized lawful bulk-export ingestion with canonical columns, transformation provenance and an independently declared source total.
- Added explicit national-ingestion provenance modes for live pagination, staged HTML and normalized bulk export.
- Added safe national dashboard JSON and national registry JSONL product contracts.
- Added national dashboard/registry JSON Schemas and product safety checks preventing private paths, URLs, hashes and internal IDs from leaking.
- Added PostgreSQL migration parity.
- No real national DIFE snapshot is committed.

## v0.21.0-dev — 2026-09-23

- Added bounded, restartable national DIFE snapshot collection batches.
- Added pre-membership source-total, page-cardinality and duplicate-ID integrity checks.
- Added page-attempt audit records with raw private payload provenance.
- Added explicit failed-page requeue for recoverable collection/parser failures.
- Added hard universe abort plus fresh-run lineage for structural integrity failures.
- Added automatic finalization only when no planned or failed pages remain.
- Added PostgreSQL migration parity and execution/recovery methodology.
- No real national DIFE crawl has been executed.

## v0.20.0-dev — 2026-09-23

- Added a separately audited national DIFE snapshot universe, distinct from the stratified validation sample.
- Added seed-first full-page planning, exact page membership, source-total stability checks, duplicate-ID detection and strict national eligibility.
- Added explicit UNCLASSIFIED handling for unmapped DIFE sector labels.
- Added national district/division/sector/status rollups, district-sector shares, location quotients and sector HHI.
- Added optional safe-product integration with an eligible NATIONAL_REGISTRY cluster universe.
- Added PostgreSQL migration parity and methodology documentation.
- No live national DIFE crawl has been executed.

## v0.19.0-dev — 2026-09-23

- Added calculated evidence freshness using source vintage with observation-time fallback.
- Added export/product breadth from approved organization-scoped evidence.
- Added cross-source numeric consistency diagnostics for employment, machines and capacity.
- Added first-to-latest numeric change signals across validated source versions without causal interpretation.
- Added declared-universe district × sector context with explicit protection against national cluster claims from the stratified validation sample.
- Bumped the safe product contract to schema v1.1 and added a backward-preserving v1.1 JSON Schema.

## v0.18.0-dev — 2026-09-23

- Added a strict versioned product payload between the private database and frontend/API consumers.
- Added approved-field allowlisting and fail-closed protection against raw paths, source URLs, internal IDs, hashes and parser internals.
- Added calculated employment scale, export-evidence breadth and employment-consistency diagnostics, all explicitly labeled CALCULATED.
- Added one-establishment and whole-validation-feed product interfaces.
- Added safe JSON and JSONL feed writers.
- Added a formal JSON Schema for product establishment payload v1.0.

## v0.17.0-dev — 2026-09-23

- Added typed BGMEA/EPB observations for employment, machines, capacity, products, HS codes, markets, certifications and registrations.
- Added explicit SITE versus ORGANIZATION scope to every typed observation.
- Added linkage safeguards so organization-only matches cannot propagate site attributes.
- Added product-facing establishment intelligence profiles with source, match type, scope, raw value, parsed value and vintage.
- Added PostgreSQL migration parity for typed and linked intelligence observations.
- Expanded the standalone dashboard preview to show typed site and organization evidence.

## v0.16.0-dev — 2026-09-23

- Added deduplicated BGMEA/EPB external-detail retrieval orchestration.
- Added failure/status tracking for source-detail requests.
- Added a fetch-to-resolution controller that reruns candidate matching after richer external profiles are staged and applies only unambiguous auto-selected links.
- Added a standalone root `index.html` dashboard preview with synthetic records and no private data dependency.

## v0.15.0-dev — 2026-09-23

- Added BGMEA general-member index parsing with source-reported totals, pagination and stable /member/<id> keys.
- Added EPB exporter-index parsing for rendered HTML and structured staged JSON, preserving numeric exporter IDs rather than slugs.
- Added seed-first external index manifests, immutable page snapshots and append-only row versions.
- Added index QC for duplicate keys, missing names and detail-URL/key integrity.
- Added targeted external detail-fetch planning from the validated DIFE sample.
- Added fetch-once/use-many request deduplication when one external record is shortlisted for several DIFE establishments.
- Added PostgreSQL migration parity for source-index and detail-request structures.

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
