# Candidate discovery workflow — v0.8

The goal of candidate discovery is to build a sufficiently large, auditable pool of **publicly exposed DIFE establishment IDs** from which the 2,000-record validation sample can be frozen.

This stage is deliberately separate from detail-page collection.

## Why two stages

DIFE sector universes differ greatly in size. Taking only the first pages would introduce ordering bias; hard-coding internal sector IDs would make the collector brittle. The discovery engine therefore uses the live filter taxonomy and current source-reported result counts.

## Stage A — live taxonomy capture

1. Stage the current public establishment-list/filter page.
2. Parse every current `INDUSTRIAL_SECTOR` option and preserve both its human-readable label and its current source value.
3. Never treat the numeric source value as a permanent business identifier.
4. Create one page-1 **UNIVERSE_SEED** request for each exposed sector option.

No sequential establishment IDs are generated.

## Stage B — universe sizing

For each staged seed page:

1. Parse the source-reported total number of matching records.
2. Create a `SectorUniverse` observation with:
   - sector family;
   - source sector label;
   - current source sector value;
   - source-reported total.
3. Persist the exact source URL and source snapshot.

If the page total cannot be parsed, stop that sector rather than guessing.

## Stage C — deterministic spread-page plan

The validation target is 2,000 establishments. Candidate discovery defaults to a **1.5× candidate multiplier**, aiming for roughly 3,000 candidates before geography/sector checks.

Within each validation sector family:

1. allocate the candidate-pool target proportionally to current source-reported sector-universe sizes;
2. preserve at least one page for every non-empty source sector;
3. choose follow-up pages at deterministic intervals across the full result range;
4. omit page 1 because the seed page is already staged.

Example: if a filtered sector contains 4,166 records and needs about 150 candidate rows, the page planner selects five pages distributed between page 1 and the final page rather than pages 1–5.

## Stage D — auditable request manifest

Before staging any follow-up page, record a request manifest in the private SQLite store:

- plan label;
- sector family;
- source sector value and label;
- page number;
- exact source URL;
- reason (`UNIVERSE_SEED` or `UNIVERSE_SPREAD`);
- status: `PLANNED`, `STAGED`, `FAILED`, or `SKIPPED`.

A request marked `STAGED` must reference an immutable source snapshot.

## Stage E — candidate-pool health check

After list pages are staged, compute:

- unique public DIFE IDs;
- candidate count by validation sector family;
- candidate count by geography group;
- sector deficits relative to the 2,000 validation quotas;
- geography deficits relative to the validation floors.

The validation sample may be frozen only when the pool has at least 2,000 unique IDs **and** the required sector/geography coverage is present.

A deficit is reported explicitly; missing candidates are never manufactured.

## Geographic supplementation

Sector-filtered discovery is the primary path. If the pool fails a geography floor, the next step is targeted sector × district supplementation using current live district filter values. This is intentionally a separate pass so the system does not explode into an unnecessary full Cartesian crawl.

## Policy gate

The public code can plan discovery and ingest already-staged HTML without making live network calls. A production unattended collector remains gated on verified automation/reuse conditions for the public source.
