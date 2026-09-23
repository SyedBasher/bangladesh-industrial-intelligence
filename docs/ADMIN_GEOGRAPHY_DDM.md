# BBS administrative geography + DDM AWARE adapter — v2.5

This layer solves a basic but important problem: public Bangladesh sources do not always use the same language, spelling or administrative-name convention.

The national industrial registry may contain Bangla district/upazila names while another official source uses English names. Joining them by loose string similarity would create silent geographic errors.

## Canonical geography

The canonical reference is designed around Bangladesh Bureau of Statistics geocodes.

BBS publishes geographic codes down to union/ward level. The v2.5 model currently uses the levels needed by the industrial/exposure product:

- division;
- district;
- upazila.

The normalized staging format retains both English and Bangla names plus BBS component codes.

The product constructs an internal public reference such as:

`BBS:DIST:<division-code>:<district-code>`

or:

`BBS:UPZ:<division-code>:<district-code>:<upazila-code>`

These are project composite references built from BBS code components. They are not presented as a separate official BBS identifier format.

## No fuzzy matching

Canonical resolution can use:

1. exact canonical English name;
2. exact canonical Bangla name;
3. an explicitly approved source-specific alias.

The resolver does not use edit-distance or general fuzzy matching.

For example, a misspelling such as `Gajipur` is not silently treated as `Gazipur`.

## Approved aliases

Aliases are auditable records with:

- administrative level;
- source spelling;
- canonical BBS geography reference;
- source name;
- explanatory note.

Initial DDM-specific examples cover known naming variants such as a shortened `Nawabganj` label resolving to canonical `Chapai Nawabganj` when the BBS unit exists.

Aliases are never global guesses. They are source-specific reviewed mappings.

## BBS source staging

The code accepts a normalized CSV intermediary with:

```text
division_code
division_name_en
division_name_bn
district_code
district_name_en
district_name_bn
upazila_code
upazila_name_en
upazila_name_bn
```

The repository does not contain the full BBS geography dataset.

A real import should preserve the source vintage and document the transformation from the official BBS geocode publication/export.

## First real exposure adapter: DDM AWARE

The Department of Disaster Management's AWARE Risk Information page publishes a district table with:

- Division
- District
- Climate zone
- Hazard Exposure
- Vulnerability
- Lack of Coping Capacity
- Risk

The adapter parses staged HTML for that documented table shape.

It does not perform live unattended collection.

## Source categories remain source categories

DDM publishes ordinal text such as:

- Very Low
- Low
- Medium
- High
- Very High

The adapter preserves these strings exactly.

It does **not** convert them to 1–5, calculate averages, or create a composite risk score.

Five district-context observations are generated from each successfully mapped DDM row:

- `DDM_HAZARD_EXPOSURE`
- `DDM_VULNERABILITY`
- `DDM_LACK_COPING_CAPACITY`
- `DDM_RISK_CATEGORY`
- `DDM_CLIMATE_ZONE`

The first four are DDM-published categories. Climate zone is retained as published context.

All are:

`domain = DISASTER_RISK`

`spatial_scope = DISTRICT`

`attribution = DISTRICT_CONTEXT`

`direction = CONTEXT_ONLY`

This prevents the product from treating the DDM category as a site-specific factory observation.

## Cross-language join

The intended join is:

```text
DIFE row: গাজীপুর
       ↓
BBS canonical district
BBS:DIST:<division>:<district>
       ↑
DDM row: Gazipur
```

The exposure engine then links through the canonical geography rather than English/Bangla string equality.

## Unresolved geography is retained

If a DDM district cannot be resolved uniquely, the row is not silently discarded or forced to the nearest name.

The import audit records:

- source division;
- source district;
- match status.

The exposure observations are created only for resolved districts.

## Provenance boundary

The private store retains:

- DDM source reference;
- source vintage;
- observed/imported timestamps;
- number of source records;
- mapped district count;
- unresolved geography list.

Public product exposure rows may contain the canonical BBS geography reference and match type, but not the private source URL/reference or internal IDs.

## Current status

The parser and crosswalk are validated with small repository fixtures.

No full BBS geography dataset and no real DDM AWARE extract are committed to GitHub.

## Next step

The next useful step is to stage the complete current BBS district/upazila crosswalk privately and run a **64-district DDM mapping audit**.

That audit should require:

- all 64 DDM district rows parsed;
- 64/64 unique districts;
- zero ambiguous mappings;
- every alias explicitly reviewed;
- no duplicate canonical district assignment;
- DDM source-category validation.

Only after that mapping audit passes should the DDM layer feed a real national industrial exposure view.
