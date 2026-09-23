# Analytical intelligence engine — v1.9

The v1.9 engine adds calculated intelligence to the safe product contract without changing source observations.

Every output is marked `CALCULATED`, includes its rule, and keeps the underlying universe or source basis visible.

## Evidence freshness

The engine uses the most recent parseable source-reported vintage where available, falling back to retrieval/observation time.

Bands:

- `CURRENT`: 180 days or less;
- `AGING`: 181–365 days;
- `STALE`: more than 365 days;
- `UNKNOWN`: no parseable date.

These thresholds are product diagnostics, not source-quality ratings.

## Export and product breadth

For approved organization-scoped evidence the engine counts distinct:

- HS codes;
- products;
- export markets;
- contributing export-evidence sources.

The result measures **evidence breadth**, not export value, shipment frequency, market share or factory-level production.

## Cross-source numeric consistency

For site-attributable numeric observations of the same type, the engine compares distinct source values.

Initial types:

- employment;
- machine count;
- production capacity.

Relative spread is:

`(maximum - minimum) / mean × 100`

Diagnostic bands:

- ≤10%: `CONSISTENT`;
- >10–25%: `MODERATE_DIFFERENCE`;
- >25%: `MATERIAL_DIFFERENCE`;
- fewer than two usable sources: `NOT_CHECKED`.

This flags disagreement for review. It does not decide which source is correct.

## Change through source versions

For site-attributable numeric observations, the engine can compare the first and latest linked observation from the **same source**.

It reports:

- first value;
- latest value;
- absolute change;
- percentage change where defined;
- first/latest observation dates;
- unit.

A changed reported value is deliberately not called growth, decline, expansion or contraction. Source methodology, reporting scope or establishment coverage may also have changed.

## Cluster context

Cluster context always declares its comparison universe.

For a district × sector cell it reports:

- universe size;
- establishments in the district;
- establishments in the sector;
- establishments in the district-sector cell;
- cell share of district establishments;
- cell share of sector establishments.

The current frozen 2,000-record validation sample is stratified. Therefore its cluster output is labeled:

`universe_kind = VALIDATION_SAMPLE`

and:

`suitable_for_national_cluster_claim = false`

It may be used to inspect validation composition, not to state that a district is nationally concentrated in an industry.

When a sufficiently complete national DIFE snapshot is available, the same function can run with:

`universe_kind = NATIONAL_REGISTRY`

Only then may the output support national descriptive cluster claims.

## Product contract v1.1

The safe product payload is now version `1.1`.

New calculated fields:

- `evidence_freshness`
- `export_product_breadth`
- `external_numeric_consistency`
- `change_signals`
- `cluster_context`

The v1.0 schema remains in the repository for backward reference. The v1.1 schema is:

`schemas/product_establishment_v1_1.schema.json`

## What this engine does not yet claim

The current layer does not infer:

- supplier relationships;
- firm ownership networks;
- export value;
- customer concentration;
- financial distress;
- closure risk;
- causal employment growth;
- national industrial clusters from the validation sample.

Those require additional data or a stronger universe.

## Next analytical layer

After national DIFE coverage and richer external history are available, the next useful measures are:

- national district-sector concentration;
- location-specific industrial density;
- product/HS specialization;
- exposure to common export markets;
- environmental/regulatory overlap;
- supplier/customer network evidence where public data support it;
- first- and second-order disruption exposure.

These should remain decomposable rather than collapsed into an opaque composite score.
