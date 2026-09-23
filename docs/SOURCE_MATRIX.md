# External enrichment source matrix — v0.3

Verified against public pages on 2026-09-23. These are source capabilities, not guaranteed coverage rates for the DIFE universe.

| Source | Public fields demonstrated | Intended linkage level | Stable key rule | Refresh approach | Current production gate |
|---|---|---|---|---|---|
| EPB Exporter Database | exporter/category, factory address, thana, district, HS codes, office address, published/updated dates | site when factory geography agrees; otherwise organization | numeric `/exporter/<id>`; never the slug | refresh matched detail page; retain EPB `Updated` date | automation/reuse policy not yet verified |
| BGMEA | member/company, BGMEA reg no, EPB reg no, factory address, mailing address, factory type, employees, machines, yearly capacity, certifications, principal products, establishment date | often factory/site | numeric `/member/<id>` plus BGMEA reg no as source field | list discovery + matched detail refresh | automation/reuse policy not yet verified |
| BKMEA | membership no, company, member type, category, owner; public 2026 member search | organization by default | membership no; detail URL if verified | membership-list refresh; site enrichment only from a public site-specific detail record | automation/reuse policy not yet verified |
| BEPZA | enterprise, investing country, products, zone page | zone-enterprise; DIFE plant only after evidence | `zone + enterprise name` unless BEPZA exposes a stronger public key | refresh each EPZ/EZ investor page independently | automation/reuse policy not yet verified |
| DoE ECC | client ID, project/industry name, address, environmental category | project/site candidate | DoE client ID | targeted name search; keep duplicate client IDs as separate official observations | search presence is not proof of a current certificate; certificate verification is separate |

## Critical interpretation rules

1. External organization attributes never propagate to all DIFE plants automatically.
2. Exporter status may attach to the organization while HS/product/site fields remain source-specific until the factory is matched.
3. BGMEA/BKMEA association membership is not a DIFE licence-status substitute.
4. BEPZA zone membership does not by itself establish a one-to-one DIFE site match.
5. DoE environmental category is an official search observation. A current clearance flag requires certificate verification, not merely search presence.
6. Missing external records remain missing; no negative status is inferred from a failed or absent match.
