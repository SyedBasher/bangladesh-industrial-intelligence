# National DIFE analytical universe — v2.0

The validation sample and the national analytical universe serve different purposes.

The 2,000-record validation sample tests parsers, matching, coverage and data quality. It is stratified by design and must not be used to estimate national industrial concentration.

The v2.0 national layer creates a separately audited, dated DIFE list-page snapshot.

## Snapshot lifecycle

A national run follows:

```text
seed page
   ↓
read source-reported total
   ↓
plan every page
   ↓
stage each exact page
   ↓
retain page → snapshot → establishment membership
   ↓
strict QC
   ↓
eligible national universe
```

No page range is guessed.

## Strict eligibility

A run is eligible for national analysis only when all of the following are true:

- every planned page is staged;
- no planned page failed or was skipped;
- every staged page reports the same source total as the seed page;
- page membership contains no duplicated DIFE public ID across pages;
- raw membership rows equal the expected source total;
- unique DIFE public IDs equal the expected source total.

If the public registry changes during pagination and the total drifts, the run fails national eligibility. The evidence is retained and a fresh run can be attempted.

This is deliberately stricter than silently accepting a near-complete crawl.

## Exact membership

A national universe is not defined as "whatever establishments happen to be in the database."

Every member is tied to:

- universe;
- source page;
- immutable DIFE page snapshot;
- exact establishment observation.

This prevents later data collection from changing the historical composition of a dated national snapshot.

## Sector mapping

Both are retained:

- source-native DIFE industrial-sector label;
- analytical sector family when an explicit mapping exists.

Unknown labels become:

`UNCLASSIFIED`

They are not assigned to `OTHER_MANUFACTURING` merely to make totals convenient.

Mapping coverage is reported as a national QC/analytics field.

## National rollups

An eligible universe can produce:

- national establishment count;
- district and division establishment counts/shares;
- source-native sector counts;
- analytical sector-family counts;
- status distribution;
- district × sector cells;
- district-sector share of district;
- district-sector share of the national sector;
- location quotient;
- sector HHI across districts.

Location quotient is:

```text
(district-sector establishments / all establishments in district)
----------------------------------------------------------------
(national sector establishments / all national establishments)
```

A value above one means that the sector has a larger share of establishments in the district than it has nationally. It is a descriptive concentration measure, not a causal or performance score.

Sector HHI is the sum of squared district shares within the sector. The underlying district-sector shares remain available; HHI is not used as an opaque composite rating.

## What the list universe cannot establish

The national list pages do not by themselves support complete national measures of:

- worker employment;
- machines;
- production capacity;
- establishment type/factory composition when type is detail-only;
- licence-expiry distribution when expiry is detail-only.

Those require national detail-page coverage or another validated source. The product should show coverage before aggregating such fields.

## Product integration

A product establishment profile can optionally request an eligible national universe.

When supplied, cluster context is returned with:

`universe_kind = NATIONAL_REGISTRY`

and:

`suitable_for_national_cluster_claim = true`

If no eligible national universe is supplied, the profile continues to use validation-sample context and remains explicitly unsuitable for national cluster claims.

## Live collection boundary

This layer provides planning, staging, versioning and QC machinery. It does not by itself authorize an unattended DIFE national crawl.

The existing DIFE source-access policy gate remains in force.

## Next step

Once a real national snapshot can be lawfully staged and passes the strict gate, the next analytical layer is:

- national district-sector concentration;
- industrial geography and density after adding defensible geographic denominators;
- national status and source-sector composition;
- coverage-aware employment/capacity aggregation;
- location exposure to climate, logistics, power and other external shocks;
- second-order exposure only where supplier/customer or common-market evidence exists.
