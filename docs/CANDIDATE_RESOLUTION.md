# External candidate search and resolution — v1.4

The enrichment layer separates **candidate retrieval** from **match classification**.

A candidate shortlist is only a set of external records worth evaluating. It is not evidence that any candidate is the same organization or factory.

## 1. Local staged-source index

For each external source, the engine first works from the currently staged source records.

It builds an in-memory blocking index using:

- exact normalized company core;
- informative normalized company-name tokens.

Corporate terms such as `limited`, `ltd`, `company`, `industries`, `group` and `bangladesh` are removed from the company core before blocking.

This avoids comparing every DIFE target against every staged source record.

Blocking is deterministic and is used only to reduce the search universe.

## 2. Transparent shortlist priorities

A blocked record is shortlisted only when the evidence meets one of five explicit retrieval classes:

1. `P1_EXACT_NAME_SITE` — exact normalized company core plus site/geography support;
2. `P2_EXACT_NAME` — exact normalized company core without usable site evidence;
3. `P3_STRONG_NAME_SITE` — strong name evidence plus site/geography support;
4. `P4_STRONG_NAME` — strong name evidence without usable site evidence;
5. `P5_WEAK_NAME_SITE` — weak name evidence only when strong site evidence also exists.

These are **shortlist priorities**, not final scores.

Within a priority class, deterministic ordering uses the disclosed name-token overlap and the external source key.

The default shortlist cap is five records per DIFE target.

## 3. Final rule-based resolution

Every shortlisted record is independently passed through the existing site-vs-organization matching rules.

Automatic resolution is deliberately narrow:

- exactly one site-level positive candidate → `AUTO_SELECTED`;
- more than one site-level positive candidate → `AMBIGUOUS`;
- no site-level positive and exactly one organization-level positive → `AUTO_SELECTED`;
- multiple organization-level positives → `AMBIGUOUS`;
- candidates exist but none passes positive-link rules → `REVIEW_REQUIRED`;
- no candidate exists in the staged source index → `NO_STAGED_CANDIDATE`.

`NO_STAGED_CANDIDATE` does **not** mean `NO_MATCH`, not an exporter, not a member, or no clearance. It only describes the current staged source index.

## 4. Two-phase application

Candidate generation does not immediately write entity links.

The workflow is:

```text
staged external index
        ↓
candidate run
        ↓
shortlist + evidence
        ↓
resolution outcome
        ↓
AUTO_SELECTED only
        ↓
apply_auto_resolutions()
        ↓
entity link + full match evidence
```

`AMBIGUOUS` and `REVIEW_REQUIRED` outcomes remain unresolved until reviewed.

This makes it possible to inspect the candidate run before modifying the entity-link layer.

## 5. Audit records

Each candidate run stores:

- validation label;
- source;
- generation time;
- shortlist cap;
- number of staged source records;
- eligible DIFE targets considered;
- number of shortlisted records;
- number auto-selected;
- number ambiguous;
- number requiring review;
- number with no staged candidate.

Each candidate stores:

- DIFE establishment;
- source record;
- shortlist position;
- priority class;
- name strength;
- name-token overlap;
- district result;
- upazila result;
- address result;
- address overlap.

Each DIFE target also receives one append-only resolution outcome.

## 6. Ambiguity is a feature, not an error

If two BGMEA profiles both have the same company name and both point to geography consistent with one DIFE establishment, the engine does not choose the first or highest-ID record.

It records `AMBIGUOUS`.

Additional identifiers, address detail, source-specific registration numbers or manual review are then required.

## 7. Reproducibility

Candidate runs are append-only.

If new source records are staged later, a new candidate run can be generated. The earlier shortlist and resolution outcome remain available for audit.

Applying an already-applied `AUTO_SELECTED` outcome is idempotent and does not create a second entity link.

## 8. Next scaling step

The candidate engine now resolves records efficiently **after an external source index has been staged**.

The next operational layer is source-index discovery: capture the public EPB/BGMEA/BKMEA/BEPZA/DoE directory/search universe under source-specific access rules, version those source indexes, and then run the v1.4 resolver across the frozen validation sample.

The commercial objective is not to maximize automatic matches. It is to maximize defensible links while keeping ambiguity visible.
