# Bangladesh Industrial Intelligence — 2,000-establishment validation design

Version: 0.2.0  
Design date: 2026-09-23

## Purpose

This stage tests whether DIFE/LIMA can support a refreshable commercial industrial-intelligence product at useful scale before any national extraction. The 2,000 records are a deliberately stratified validation sample, not an estimate of national industrial shares.

## Primary sector targets

| Sector family | Target |
|---|---:|
| RMG & textiles | 500 |
| Food & agro-processing | 300 |
| Pharma, chemicals & plastics | 250 |
| Engineering, steel & construction materials | 250 |
| Leather & footwear | 150 |
| Logistics, warehousing & transport | 150 |
| Electrical & electronics | 100 |
| Other manufacturing | 200 |
| Non-factory establishments (control group) | 100 |
| **Total** | **2,000** |

These are validation quotas chosen for commercial relevance and source-enrichment potential. They are not population weights.

## Geographic floors

| Geography | Floor |
|---|---:|
| Dhaka industrial core | 700 |
| Chattogram industrial belt | 300 |
| Rajshahi & Rangpur divisions | 300 |
| Khulna & Barishal divisions | 250 |
| Sylhet & Mymensingh divisions | 250 |
| Other / unmatched | 200 |

Geographic floors are cross-cutting checks. They do not add another 2,000 observations.

## Candidate discovery

1. Fetch the current public DIFE establishment-list page.
2. Parse the live sector/district/status option labels and their current source values.
3. Never hard-code an internal DIFE sector ID where a live label/value can be captured.
4. For each selected industrial sector, retrieve the first public filtered page to obtain the current result count.
5. Select additional pages at deterministic intervals across that filtered result set rather than taking only the first pages.
6. Capture only public establishment IDs exposed by those public list pages.
7. Build a candidate pool larger than 2,000 (default target multiplier 1.5) so geography floors can be met without replacing sector coverage.
8. Run the deterministic sample planner and freeze the selected validation IDs before retrieving detail pages.

## Detail collection

Detail retrieval is performed only for establishments already selected into `validation_sample`.

Recommended batches:

- Batch 1: 100 detail records
- Checkpoint: parser success, HTTP errors, unexpected HTML changes
- Batch 2: next 400
- Checkpoint: field completeness and status/type mix
- Batch 3: remaining 1,500

At any checkpoint, stop if access controls, CAPTCHA, rate-limit behavior, or material page-structure changes appear.

## Fields to measure

DIFE core:

- establishment type
- source status
- licence number
- previous licence number
- registration number
- previous registration number
- licence expiry
- sector
- address
- upazila/district/division
- class
- employment total/components

External enrichment coverage:

- EPB exporter status
- EPB product / HS information
- BGMEA/BKMEA association linkage where relevant
- BGMEA/BKMEA machines/capacity/product fields where explicitly published
- BEPZA enterprise/zone linkage
- Department of Environment project/certificate linkage
- geocoding quality and administrative-boundary assignment

## Match review

External-source links must use one of:

- `EXACT_SITE`
- `PROBABLE_SITE`
- `ORGANIZATION_ONLY`
- `AMBIGUOUS`
- `NO_MATCH`
- `SOURCE_FEASIBILITY_ONLY`

A company-level exporter match must never be copied automatically to all DIFE plants.

## Go/no-go metrics for a national build

The 2,000-row validation should report, at minimum:

1. public-list parser success rate;
2. detail-page retrieval success rate;
3. non-missing rate for each DIFE core field;
4. share classified as factory vs non-factory establishment;
5. frequency of multiple establishments linked to one organization;
6. exact/probable site-match rates by external source;
7. organization-only and ambiguous-match rates;
8. external enrichment coverage by sector;
9. geography/geocoding coverage and quality;
10. change/versioning behavior on a repeat mini-refresh.

No field should be advertised as nationally available merely because it is present for one association or one sector.
