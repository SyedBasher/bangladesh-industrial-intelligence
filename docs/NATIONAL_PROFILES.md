# National District and Sector Profiles — v2.3

The national dashboard answers broad questions about the DIFE registry. District and Sector Profiles turn those national rollups into drillable product views.

Both profile types are built entirely from the safe national dashboard and national registry product contracts.

They do not query or serialize private raw snapshots, manifests, source URLs, internal IDs or collection diagnostics.

## District Profile

A District Profile contains:

- district establishment count;
- share of the national DIFE universe;
- exact national-registry coverage status;
- analytical-sector mapping coverage;
- upazila composition;
- DIFE status composition;
- source-native DIFE sector composition;
- analytical sector-family composition;
- district-sector location quotients;
- district share of each national sector;
- the share of the district accounted for by its three and five largest sector families;
- a registry drill-down filter.

The profile does not assign a single district score.

### Location-quotient flag

Each mapped district-sector cell retains the numeric location quotient and a transparent flag:

- \`ABOVE_NATIONAL_SHARE\` when LQ > 1;
- \`EQUAL_TO_NATIONAL_SHARE\` when LQ = 1;
- \`BELOW_NATIONAL_SHARE\` when LQ < 1;
- \`NOT_AVAILABLE\` when the quotient cannot be calculated.

This is descriptive specialization relative to the national registry composition. It is not a productivity or competitiveness rating.

## Sector Profile

A Sector Profile contains:

- national establishment count and share;
- number of districts in which the sector appears;
- exact registry coverage status;
- source-native DIFE labels represented inside the analytical family;
- DIFE status composition;
- district distribution;
- district share of the national sector;
- the sector's share within each district;
- location quotients;
- sector HHI across districts;
- shares accounted for by the three and five largest districts;
- a registry drill-down filter.

Again, no composite sector score is produced.

## Coverage boundaries

\`national_registry_coverage = EXACT\` means the profile was generated from an eligible \`NATIONAL_REGISTRY\` universe whose record count passed the national snapshot gate.

It does not mean every establishment has:

- DIFE detail-page fields;
- BGMEA/BKMEA membership;
- EPB exporter evidence;
- DoE evidence;
- capacity, machine or worker data;
- geocoded coordinates.

The profile therefore states:

\`external_enrichment_coverage = NOT_INCLUDED_IN_LIST_LEVEL_PROFILE\`

External-source coverage will be added later as a separate evidence layer rather than conflated with list-universe completeness.

## Drill-down

Profiles return a safe registry filter such as:

\`\`\`json
{"district": "Gazipur"}
\`\`\`

or:

\`\`\`json
{"sector_family": "RMG_TEXTILE"}
\`\`\`

The drill-down is applied to the approved national registry product feed, not the private database.

This gives the frontend a direct path:

\`\`\`text
National dashboard
      ↓
District / Sector Profile
      ↓
approved registry rows
      ↓
establishment profile
\`\`\`

## Static deployment

A profile can be written as a standalone JSON file using:

\`\`\`python
write_national_profile_json(...)
\`\`\`

Possible deployment layout:

\`\`\`text
product/
  national_dashboard.json
  national_registry.jsonl
  districts/
    gazipur.json
    dhaka.json
  sectors/
    RMG_TEXTILE.json
    FOOD_AGRO.json
\`\`\`

The filenames and distribution policy are deployment choices; the product contract remains independent of hosting provider.

## Schemas

District profile:

\`schemas/national_district_profile_v1.schema.json\`

Sector profile:

\`schemas/national_sector_profile_v1.schema.json\`

## Current-data warning

The repository still contains no real eligible national DIFE snapshot.

The standalone website demonstrates the profile behavior with synthetic values only.

## Next analytical layer

After these base profiles, the next useful extension is a coverage-aware **exposure layer** that joins location-level industrial composition to independently sourced hazards and infrastructure conditions.

That should begin with spatial/location exposure where evidence is strong, for example flood/hazard zones, transport connectivity and power-system context. Supplier/customer propagation should be added only where actual network evidence exists; co-location alone must not be treated as a supply-chain link.
