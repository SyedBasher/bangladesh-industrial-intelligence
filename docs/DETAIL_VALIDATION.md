# Detail-validation checkpoints — v1.0

After the 2,000-establishment validation sample is jointly feasible and frozen, DIFE detail-page validation proceeds in three cumulative checkpoints:

1. **100 records**
2. **500 records**
3. **2,000 records**

A later checkpoint remains locked until the earlier checkpoint passes its QC gate.

## 1. Progressive sample design

The first 100 records are not chosen by lowest DIFE public ID.

The frozen 2,000 records are grouped by their sector-family × geography cell. The detail planner builds one deterministic weighted sequence that interleaves those cells in proportion to their size in the frozen sample.

Within each cell, establishments are ordered by a stable SHA-256 key derived from:

`validation label + DIFE public ID`

This gives a reproducible sequence without giving analytical priority to old/low public IDs.

The prefixes are nested:

- positions 1–100 → first checkpoint;
- positions 101–500 → second tranche;
- positions 501–2,000 → final tranche.

Therefore the 500-record checkpoint contains the first 100, and the 2,000-record checkpoint contains the first 500.

## 2. Frozen request manifest

Every selected DIFE ID gets a frozen public detail URL of the form:

`https://lima.dife.gov.bd/public-report/establishment/<public_id>`

The detail ingester accepts HTML only when:

- the validation label and DIFE ID were already planned;
- the supplied source URL exactly equals the frozen request URL;
- the public ID embedded in the URL equals the expected DIFE public ID.

No sequential IDs are generated.

## 3. Retrieval status

Each detail request has one of:

- `PLANNED`
- `PARSED`
- `FAILED`
- `SKIPPED`

A failed request can be explicitly reset to `PLANNED` for retry. The error text remains part of the validation workflow through checkpoint decision history and collection logs.

## 4. Parser integrity vs source missingness

These are deliberately separate.

### Parser-valid

A parsed detail page is considered structurally valid when at least two independent expected anchors are present among:

- establishment identity;
- regulatory identifier;
- location;
- sector/class/type;
- DIFE status.

This detects error pages, layout breakage and empty/unexpected responses without assuming every establishment has every field.

### Core-complete

For the validation gate, a record is core-complete only when it contains:

- establishment identity;
- sector;
- DIFE status;
- district;
- establishment type;
- at least one of licence number or registration number.

Missing fields remain missing. The system never manufactures them.

## 5. Default QC gate

The default thresholds are intentionally configurable and are validation thresholds, not claims about national DIFE completeness.

| Metric | Default minimum |
|---|---:|
| Retrieval success | 95% |
| Parser-valid among retrieved pages | 95% |
| Snapshot provenance completeness | 100% |
| Frozen URL / DIFE-ID integrity | 100% |
| Core-complete among retrieved pages | 85% |

A checkpoint is also blocked while any planned request remains unresolved.

### Provenance completeness

For DIFE detail pages, the gate requires:

- immutable source snapshot ID;
- exact source URL;
- retrieval timestamp;
- SHA-256 content hash.

A source-reported page vintage is retained when the source provides one, but its absence is **not invented** and is not by itself a validation failure.

## 6. Diagnostic field coverage

The following are reported at every checkpoint but do not automatically block progression:

- employment total;
- licence-expiry field;
- licence number;
- registration number;
- district;
- sector;
- DIFE status;
- establishment type.

This distinction is important. Low employment coverage, for example, may represent genuine source missingness or non-factory establishments rather than parser failure.

If the first 100 reveal that a supposedly universal field is in fact structurally absent for some DIFE classes, the QC policy should be revised transparently before the 500-record checkpoint rather than forcing false completeness.

## 7. Gate behavior

Initial states:

```text
100  → READY
500  → LOCKED
2000 → LOCKED
```

If the 100-record gate passes:

```text
100  → PASSED
500  → READY
2000 → LOCKED
```

If it fails:

```text
100  → FAILED
500  → LOCKED
2000 → LOCKED
```

Failed requests may be retried and the failed checkpoint can be re-evaluated. It unlocks the next tranche only after a later evaluation passes.

Every evaluation stores:

- full metrics;
- the exact policy thresholds used;
- pass/fail;
- reasons;
- evaluation timestamp.

This prevents later changes to QC thresholds from rewriting what happened in an earlier validation decision.

## 8. No live collection assumption

The public repository implements planning, staged-HTML ingestion, QC and audit logic. It does not assume that public visibility alone authorizes unattended bulk collection.

Live retrieval remains a separate policy/access gate. Once that is verified, the same detail manifest and checkpoint controls can drive the collector without changing the validation methodology.
