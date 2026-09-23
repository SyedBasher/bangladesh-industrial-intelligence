# Geographic supplementation and validation freeze — v0.9

This stage closes the gap between a broad sector-based candidate pool and a defensible 2,000-establishment validation sample.

## 1. Why geographic supplementation is separate

The primary discovery pass is sector based. It is intentionally not a full district × sector crawl.

After staging the primary candidate pool, the system calculates geography deficits against the validation floors. Only deficient geography groups trigger supplemental requests.

Supplementation is two-stage:

1. **GEOGRAPHY_SEED** — a bounded first pass of selected district × sector combinations to learn their current source-reported result counts.
2. **GEOGRAPHY_SPREAD** — additional pages distributed through non-empty combinations, proportional to their observed universe sizes.

This keeps the request surface small and auditable.

## 2. How seed combinations are chosen

For each deficient geography group:

- current DIFE district filter labels/values are used;
- districts are selected at deterministic spread positions rather than taking only the alphabetically first districts;
- sector families with unresolved validation deficits are prioritized;
- within a family, source sector options with larger already-observed DIFE universes are preferred;
- the first pass is bounded by configurable maximum numbers of districts and sector options.

If the seed combinations are empty or too small, the next pass can widen the bounds. The engine does not silently expand into a national Cartesian crawl.

## 3. Request provenance

Supplement requests have their own manifest in the private SQLite store:

- plan label;
- geography group;
- DIFE district source label/value;
- sector family;
- DIFE sector source label/value;
- page;
- exact public URL;
- reason;
- status;
- linked immutable source snapshot when staged;
- error text when failed.

Statuses are `PLANNED`, `STAGED`, `FAILED`, and `SKIPPED`.

## 4. Why the final freeze is a joint allocation problem

The sector targets sum to 2,000. The geography floors also sum to 2,000.

Therefore the final validation sample must satisfy **both** systems of constraints at the same time. A sequential algorithm such as:

1. fill sector quotas;
2. add records to repair geography;
3. trim back to 2,000;

can silently break the sector quotas or the geography floors.

The v0.9 freeze engine instead solves a bipartite maximum-flow problem:

```text
source
  ↓
sector targets
  ↓
observed sector × geography candidate cells
  ↓
geography targets
  ↓
sink
```

Each sector→geography edge is capped by the number of real unique DIFE candidates observed in that cell.

A sample is frozen only if the maximum flow equals 2,000.

## 5. Failure is explicit

If the candidate pool is not feasible, the engine reports:

- total unique candidates;
- sector availability;
- geography availability;
- simple sector deficits;
- simple geography deficits;
- maximum feasible joint allocation;
- the remaining flow gap.

This catches cases where all marginal totals appear large enough but the sector × geography distribution still makes the requested design impossible.

No establishments are invented to close the gap.

## 6. Freeze semantics

The private store computes a feasible plan **before** deleting any existing sample with the same label.

Therefore a failed re-freeze cannot destroy a previously valid frozen sample.

Once feasible, the selected IDs are persisted with:

- validation label;
- DIFE public ID;
- sector family;
- geography group;
- selection stage = `JOINT_QUOTA`;
- freeze timestamp.

The deterministic rule selects the lowest public IDs inside each allocated cell after the cell allocation itself is solved. This is for reproducibility, not because low IDs have analytical priority.

## 7. Next checkpoint

After a valid 2,000-ID sample is frozen, detail collection proceeds in checkpoints:

- first 100 records;
- review parser/access/completeness results;
- expand to 500;
- review again;
- complete 2,000 only if the preceding checkpoints remain acceptable.

The detail stage must not start from an unfrozen or infeasible sample.
