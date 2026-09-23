# Product data contract — v1.8

The public-facing product must not read the private validation database directly.

The v1.8 layer creates a strict boundary:

```text
PRIVATE DATA ENGINE
raw pages + snapshots + parser state + match evidence + internal IDs
                         ↓
SAFE PRODUCT CONTRACT
approved source facts + calculated indicators + public establishment reference
                         ↓
website / API / static JSON / customer application
```

## 1. Product payload version

The initial contract is:

`schema_version = 1.1`

A formal JSON Schema is stored at:

`schemas/product_establishment_v1_1.schema.json`\n\nThe v1.0 schema is retained for backward reference.

The contract is storage-provider neutral. It can later be delivered by PostgreSQL, Supabase, Neon, Cloudflare, a conventional API, or a static JSON feed.

## 2. Approved establishment fields

The DIFE backbone can expose:

- public establishment reference, formatted as `DIFE:<public-id>`;
- establishment name;
- address;
- upazila, district and division;
- official DIFE status;
- industrial sector;
- establishment type;
- DIFE class;
- licence-expiry text;
- DIFE worker total;
- DIFE observation timestamp.

Internal database row IDs are never included.

## 3. Approved external facts

Only allowlisted typed observations are eligible for product export.

The initial allowlist includes:

- employment count;
- machine count;
- production capacity;
- principal products;
- HS codes;
- export markets;
- certifications;
- association membership evidence;
- association registration;
- export registration;
- exporter-database evidence;
- association;
- exporter category.

Every exported fact retains:

- source;
- site/organization scope;
- match type;
- whether the fact is site-attributable;
- text value;
- numeric value when parsed;
- unit;
- source-reported vintage when available;
- retrieval/observation time.

Raw parser labels and raw HTML are not exported.

## 4. Fail-closed field protection

The product builder rejects payloads containing internal/private fields such as:

- source URLs;
- raw snapshot paths;
- snapshot IDs;
- external-record/version IDs;
- entity-link IDs;
- typed-observation IDs;
- raw parser labels/values;
- content hashes;
- match-evidence IDs.

The public product is therefore generated from an allowlist rather than by serializing database rows.

## 5. Calculated indicators

Calculated fields are explicitly labeled `CALCULATED`.

### Employment scale band

The first analytical band uses worker counts only:

- `UNDER_50`
- `50_249`
- `250_999`
- `1000_PLUS`

This is an internal analytical grouping, **not** an official Bangladesh MSME/industrial classification.

DIFE worker total is preferred. If it is missing, a validated site-attributable external employment observation may provide the analytical basis.

### Export-evidence breadth

Counts the number of distinct validated external sources contributing approved export-related evidence.

Labels:

- `NONE`
- `SINGLE_SOURCE`
- `MULTI_SOURCE`

This measures evidence breadth, not export value or current shipment activity.

### Employment consistency

When DIFE and at least one site-attributable external source both report employment:

- difference ≤10% → `CONSISTENT_WITHIN_10_PERCENT`
- difference >10% to 25% → `MODERATE_DIFFERENCE`
- difference >25% → `MATERIAL_DIFFERENCE`

The exact percentage comparison is retained.

This is a diagnostic for cross-source consistency, not a declaration that either source is wrong.

## 6. One-establishment and feed interfaces

The private store now exposes two safe interfaces:

```python
store.product_establishment_payload(...)
store.product_validation_feed(...)
```

Both return only the versioned product contract.

## 7. Static product feeds

Two writers are available:

```python
write_product_json(...)
write_product_jsonl(...)
```

These accept already-built safe payloads and run the fail-closed safety check again before writing.

Generated product feeds belong in the private/deployment data layer, not in the public GitHub repository unless they contain only synthetic fixtures.

## 8. Why JSONL is useful

JSONL permits:

- streaming large establishment feeds;
- incremental indexing;
- easy import into PostgreSQL/search systems;
- simple Cloudflare/R2 delivery;
- line-by-line validation;
- regeneration without coupling the frontend to the private schema.

## 9. Product/API boundary

The website should never receive:

- parser diagnostics;
- unresolved candidates;
- ambiguous internal evidence;
- raw source snapshots;
- private paths;
- source-access policy records;
- collection-run internals.

Those remain in the research/validation layer.

Only resolved, approved facts and explicitly calculated indicators cross the product boundary.

## 10. Analytical extension in v1.1

The product contract now also permits the calculated fields documented in `docs/ANALYTICAL_INTELLIGENCE.md`:

- evidence freshness;
- export/product breadth;
- cross-source numeric consistency;
- first-to-latest reported-value change signals;
- explicitly declared-universe cluster context.

The website still receives only the safe product contract. Historical source rows and private cluster-building inputs remain behind the product boundary.

The next step is to move from validation-sample context toward a **national analytical universe** once the DIFE national snapshot can be staged and validated, then add second-order exposure modules only where public evidence supports them.
