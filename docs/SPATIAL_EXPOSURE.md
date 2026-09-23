# First-order spatial exposure intelligence — v2.4

The exposure layer links independently sourced hazard and infrastructure observations to the national industrial registry.

It is deliberately limited to **first-order exposure context**.

The system does not infer suppliers, customers, input dependencies or propagation chains from co-location.

## Supported domains

The initial normalized domains are:

- \`CLIMATE_HAZARD\`
- \`TRANSPORT_ACCESS\`
- \`POWER_SYSTEM\`
- \`ENVIRONMENTAL_REGULATORY\`

A source observation retains its own metric code, label, value, unit, vintage and evidence note.

No cross-domain composite exposure score is produced.

## Spatial scope

Every observation must declare one of three scopes.

### SITE

Requires an explicit public establishment reference such as:

\`DIFE:12345\`

The resulting attribution is:

\`SITE_SPECIFIC\`

### UPAZILA

Requires both district and upazila.

The match is exact after conservative whitespace/case normalization.

The resulting attribution is:

\`UPAZILA_CONTEXT\`

This describes conditions in the surrounding upazila. It does not establish that the factory site itself experienced the condition.

### DISTRICT

Requires a district.

The resulting attribution is:

\`DISTRICT_CONTEXT\`

Again, this is area context, not a claim about the specific factory footprint.

## No fuzzy geography in v1

The first version does not fuzzy-match place names, infer aliases, geocode free text, or bridge transliteration variants automatically.

A source value such as \`Gazipur District\` will not silently match a registry value of \`Gazipur\`.

Geographic normalization can be added later through a separately reviewed administrative-geography crosswalk.

## Exposure direction

A metric may declare:

- \`HIGHER_MEANS_MORE_EXPOSURE\`
- \`HIGHER_MEANS_LESS_EXPOSURE\`
- \`CONTEXT_ONLY\`

This direction is metadata. It does not convert the metric into a common score.

For example, outage hours and travel time may both have \`HIGHER_MEANS_MORE_EXPOSURE\`, but their units and substantive meanings remain separate.

## Evidence coverage is not risk prevalence

The exposure coverage calculation asks:

> What share of registry establishments has at least one linked exposure observation?

It does **not** ask:

> What share of establishments is harmed or at risk?

A district-level climate observation may contextualize every establishment in that district, producing 100% evidence coverage for that metric. That does not mean 100% of sites flooded.

## Establishment Exposure Profile

The establishment profile contains:

- public DIFE reference;
- name and geography;
- sector family;
- linked observations;
- source;
- domain;
- metric;
- spatial scope;
- attribution;
- source vintage;
- observed value and unit;
- whether any evidence is site-specific;
- whether any evidence is area context.

Area context and site evidence remain visibly distinct.

## District Exposure Profile

The district profile reports:

- registry establishments in the district;
- share with any linked exposure evidence;
- coverage by domain;
- coverage by spatial scope;
- distinct source/metric/geography conditions;
- number of establishments contextualized by each condition.

All counts are establishment-weighted.

They are not weighted by:

- employment;
- output;
- exports;
- assets;
- production capacity;
- expected monetary loss.

Those weights require substantially better national coverage.

## Sector Exposure Profile

The sector profile reports:

- sector establishment count;
- overall evidence coverage;
- evidence coverage by domain and scope;
- district-by-district coverage;
- distinct conditions linked to sector establishments.

A sector with high evidence coverage is not automatically more exposed than a sector with low coverage. It may simply have better source coverage.

## Private source provenance

The private store retains source authority, methodology and an optional source reference.

The public product contract excludes the private source reference and all internal observation IDs.

## Product safety

The exposure outputs reuse the national product safety boundary.

They cannot contain:

- internal database IDs;
- source URLs;
- private artifact paths;
- raw snapshots;
- content hashes;
- private manifests.

## Schemas

Establishment exposure profile:

\`schemas/establishment_exposure_profile_v1.schema.json\`

District exposure profile:

\`schemas/district_exposure_profile_v1.schema.json\`

Sector exposure profile:

\`schemas/sector_exposure_profile_v1.schema.json\`

## Current status

The repository contains only synthetic exposure fixtures for tests and preview behavior.

No real hazard, transport, grid or environmental dataset is committed.

## Next step

The next step is to add **source-specific exposure adapters and geographic crosswalks** one domain at a time.

The first source should be chosen for:

1. public and lawful reuse;
2. stable national coverage;
3. documented spatial unit and vintage;
4. machine-readable or reproducibly staged data;
5. a metric whose meaning can be retained without inventing a proprietary score.

Only after first-order exposure coverage is established should the platform add second-order propagation, and then only where actual supplier/customer/common-market evidence exists.
