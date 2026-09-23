# Entity matching rules — v1.3

The matching layer separates **organization identity** from **establishment/site identity**. It does not publish a single opaque confidence score.

## Candidate generation

Name similarity is used only to produce a small review shortlist. The final match class is rule-based and records each component separately.

## Evidence stored

- name: exact normalized company core / strong / weak / missing
- district: match / conflict / missing
- upazila: match / conflict / missing
- address: informative-token overlap and Jaccard value
- source-specific identifiers when present

## Match classes

**EXACT_SITE** — company identity is strong, district agrees, and upazila or address evidence also agrees.

**PROBABLE_SITE** — company identity is strong and geography is consistent, but the address evidence is incomplete or less specific.

**ORGANIZATION_ONLY** — company identity is strong, but the external source has no site geography or its factory geography conflicts with the DIFE establishment. Organization-level fields may be linked; plant-level fields may not.

**AMBIGUOUS** — multiple plausible source records cannot be resolved without additional evidence. This is a review state, not a best-guess match.

**NO_MATCH** — available evidence is insufficient or inconsistent.

**SOURCE_FEASIBILITY_ONLY** — source capability was tested without asserting an entity match.

## Non-negotiable rules

- No company-name-only plant match.
- No district centroid or administrative centroid is treated as a factory coordinate.
- No external source overwrites DIFE official fields.
- No expired DIFE licence is automatically converted to inactive/closed.
- No missing external match is interpreted as “not an exporter”, “not a member”, or “no environmental clearance”.


## Implemented v1.3 safeguards

- Source eligibility is evaluated before matching; out-of-scope is not treated as a negative business fact.
- BKMEA is capped at organization-level linkage by default.
- EPB, BEPZA and DoE require site evidence before plant-level attributes can propagate.
- BGMEA may support site-level linkage when its factory geography agrees with DIFE.
- Address overlap is retained as an explicit component value rather than collapsed into a hidden score.
- Every reviewed link stores the rule version and all component evidence.
