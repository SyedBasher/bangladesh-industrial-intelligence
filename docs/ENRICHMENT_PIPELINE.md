# External enrichment pipeline — v0.3

## Flow

1. Freeze the DIFE validation sample.
2. Determine source eligibility by sector/site type for query efficiency. Eligibility is a search scope, not a factual claim.
3. Stage immutable public-source HTML/search results.
4. Parse source-native fields without filling blanks.
5. Store source record + immutable version + source URL + retrieval time + source update time when supplied.
6. Generate candidate entity pairs using normalized names.
7. Apply transparent site-vs-organization matching rules.
8. Store component evidence for every accepted/rejected link.
9. Calculate coverage separately for each source and each sector/geography scope.
10. Promote a field into the commercial MVP only after the 2,000-record validation establishes adequate coverage and error rates.

## Collection modes

External adapters default to **staged HTML or policy-verified live retrieval**. This is deliberate: the public pages are suitable for feasibility testing, but the package does not assume that public visibility alone grants permission for unattended bulk collection or commercial redistribution.

## Refresh design

Each external record is versioned using a content hash. Source-provided update dates are retained when available. A refresh creates a new observation when content changes; it does not overwrite history.
