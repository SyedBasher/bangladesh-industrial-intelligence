# External enrichment source matrix — v1.3

Verified against public pages on 2026-09-24. These are source capabilities, not guaranteed coverage rates for the DIFE universe.

| Source | Public fields demonstrated | Intended linkage level | Stable key rule | Refresh approach | Current production gate |
|---|---|---|---|---|---|
| EPB Exporter Database | exporter/category, factory address, thana, district, HS codes, office address, published/updated dates | site when factory geography agrees; otherwise organization | numeric `/exporter/<id>`; never the slug | refresh matched detail page; retain EPB `Updated` date | staged parser implemented; live automation/reuse policy not yet verified |
| BGMEA | member/company, BGMEA reg no, EPB reg no, factory address, mailing address, factory type, employees, machines, yearly capacity, certifications, principal products, establishment date | often factory/site | numeric `/member/<id>` plus BGMEA reg no as source field | list discovery + matched detail refresh | automation/reuse policy not yet verified |
| BKMEA | membership no, company, member type, category, owner; public 2026 member search | organization by default | membership no; detail URL if verified | membership-list refresh; site enrichment only from a public site-specific detail record | automation/reuse policy not yet verified |
| BEPZA | enterprise, investing country, products, zone page | zone-enterprise; DIFE plant only after evidence | `zone + enterprise name` unless BEPZA exposes a stronger public key | refresh each EPZ/EZ investor page independently | automation/reuse policy not yet verified |
| DoE ECC | client ID, project/industry name, address, environmental category | project/site candidate | DoE client ID | targeted name search; keep duplicate client IDs as separate official observations | staged parser implemented; search presence is not proof of a current certificate; certificate verification is separate |

## Critical interpretation rules

1. External organization attributes never propagate to all DIFE plants automatically.
2. Exporter status may attach to the organization while HS/product/site fields remain source-specific until the factory is matched.
3. BGMEA/BKMEA association membership is not a DIFE licence-status substitute.
4. BEPZA zone membership does not by itself establish a one-to-one DIFE site match.
5. DoE environmental category is an official search observation. A current clearance flag requires certificate verification, not merely search presence.
6. Missing external records remain missing; no negative status is inferred from a failed or absent match.


## Geography and exposure sources

| Source | Public fields demonstrated | Role | Geographic linkage | Current production gate |
|---|---|---|---|---|
| BBS geocodes | official geographic codes down to union/ward level; district/upazila codes and names are also published in census community reports | canonical administrative geography | exact English/Bangla canonical names plus reviewed aliases | normalized staging adapter implemented; full current crosswalk still to be staged privately |
| DDM AWARE Risk Information | division, district, climate zone, Hazard Exposure, Vulnerability, Lack of Coping Capacity, Risk | first-order district disaster-risk context | DDM district → canonical BBS district → DIFE establishment geography | staged HTML parser and BBS-linked adapter implemented; real 64-district mapping audit still pending |

### Exposure interpretation rules

1. DDM district categories remain source text; they are not converted to numeric scores.
2. A district DDM observation becomes `DISTRICT_CONTEXT`, not a site-specific factory event.
3. English/Bangla joins must resolve through canonical BBS geography or an explicitly approved alias.
4. Unresolved or ambiguous geographies remain unresolved and are reported; they are never fuzzy-matched.
5. BBS code-component composites such as `BBS:DIST:<division>:<district>` are project references built from BBS components, not a claim that BBS publishes that exact concatenated identifier.
