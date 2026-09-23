# BGMEA and EPB source-index discovery — v1.5

The external matching engine should not begin by downloading every external detail page.

The v1.5 workflow first captures each public **directory/index universe**, versions those minimal records, and uses the index to decide which detail pages are worth staging for the frozen DIFE validation sample.

## 1. BGMEA public index

The public general-member directory exposes:

- a source-reported total member count;
- pagination;
- member/company name;
- BGMEA registration number;
- a public member detail link.

The stable index key is the numeric ID in:

`/member/<id>`

The BGMEA registration number is retained as a source field but is not substituted for the public member-page ID.

The parser reads the source-reported total and actual page links rather than hard-coding the number of members or pages. This matters because the directory changes over time.

## 2. EPB public index

EPB exposes its exporter directory at the public exporter-database site.

Exporter detail URLs use:

`/exporter/<numeric-id>/<slug>`

The numeric exporter ID is the identity key. The slug is display/navigation text and is never used as the stable key.

The EPB public directory may be client-rendered. The index layer therefore supports two staged representations:

- rendered HTML containing public exporter links;
- structured JSON captured from a lawful/public representation of the directory.

The parser does not depend on a private or undocumented API. If pagination metadata is not present in the staged representation, only the seed page is authorized until page bounds are established.

## 3. Seed-first pagination

Every index run begins with one seed page.

```text
create run
   ↓
stage page 1
   ↓
read source-reported total / last page
   ↓
expand request manifest
   ↓
stage remaining planned pages
   ↓
QC
   ↓
finalize index run
```

No page range is guessed.

## 4. Immutable page and row versions

Each staged index page receives an immutable source snapshot with:

- source URL;
- retrieval timestamp;
- content hash;
- parser version;
- source-reported total when available;
- private raw-payload path when retained.

Each directory row has:

- stable source key;
- company/exporter name;
- detail URL;
- source registration number where exposed;
- factory/office geography where exposed.

Changed rows create new versions rather than overwriting the historical observation.

## 5. Index QC

An index run cannot be treated as complete while planned pages remain unresolved.

Final QC checks:

- number of structured records;
- duplicate stable keys across staged pages;
- missing names;
- detail URL ↔ stable-key integrity;
- unique normalized company-name cores;
- failed/staged page counts.

A duplicate key across different staged pages fails the run because a changing paginated directory may have shifted while the run was in progress. A fresh run can then be staged rather than silently deduplicating away the evidence.

## 6. Detail-fetch minimization

After an index passes QC, eligible DIFE establishments are blocked against the index using the existing normalized company-core/token machinery.

Only the top transparent shortlist candidates generate external detail requests.

This changes the workload from:

```text
download every BGMEA/EPB detail page
        ↓
try to match afterward
```

to:

```text
version directory index
        ↓
block 2,000 DIFE validation records
        ↓
shortlist plausible external records
        ↓
fetch only those external detail pages
        ↓
run full site-vs-organization resolution
```

## 7. Fetch once, use many times

One external member/exporter may be shortlisted for more than one DIFE establishment.

The external detail request is unique by:

`source + stable source key + detail URL`

A join table records every DIFE target that requested that detail.

Therefore the source page is staged once and can be evaluated against several candidate DIFE sites.

## 8. No negative inference

If a DIFE establishment produces no index candidate, that means only:

**no plausible candidate was found in the currently staged source index.**

It does not mean:

- not a BGMEA member;
- not an EPB exporter;
- not active;
- not export-oriented.

The source-index run itself must first be complete and pass QC before its absence can even be interpreted as directory absence, and directory absence still is not automatically a negative business fact.

## 9. Live collection remains source-specific

The v1.5 code provides index parsers, manifests, versioning and detail-request planning.

It does not override the source-specific access-policy gate. Any unattended BGMEA or EPB index collection requires its own documented review.

## 10. Next step

Once BGMEA and EPB indexes can be staged reproducibly, the same source-index abstraction can be extended to BKMEA, BEPZA and DoE.

The immediate analytical workflow then becomes:

```text
DIFE validation sample
        +
BGMEA / EPB source index
        ↓
targeted external detail pages
        ↓
v1.4 candidate resolution
        ↓
validated site/org links
        ↓
capacity / product / HS / export-exposure variables
```
