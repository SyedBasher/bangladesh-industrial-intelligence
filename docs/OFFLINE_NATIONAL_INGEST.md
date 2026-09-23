# Offline national ingestion and product feeds — v2.2

A national DIFE universe does not have to originate from live automated collection.

The v2.2 layer supports three declared ingestion modes:

- \`LIVE_PAGINATED\`
- \`STAGED_HTML_ARCHIVE\`
- \`NORMALIZED_BULK_EXPORT\`

All three converge on the same strict national-universe QC and analytical engine.

## 1. Staged HTML archive

A fixed private archive contains:

- one manifest;
- every DIFE list page required for the snapshot;
- optional SHA-256 hashes for each page.

Example manifest:

\`\`\`json
{
  "format_version": "1.0",
  "universe_label": "dife_2026_09_archive",
  "seed_url": "https://lima.dife.gov.bd/public-report/establishment-list?page=1",
  "page_size": 30,
  "created_at": "2026-09-24T03:00:00+06:00",
  "pages": [
    {
      "page": 1,
      "file": "page_00001.html",
      "retrieved_at": "2026-09-24T03:01:00+06:00",
      "sha256": "..."
    }
  ]
}
\`\`\`

The importer stages page 1 first, reads the source-reported total, derives the complete expected page set, and then requires the archive manifest to contain exactly that set.

An archive with missing or extra page numbers is rejected.

## 2. Archive integrity

For each page the importer can verify the manifest hash before parsing.

The existing national integrity rules still apply:

- stable source-reported total;
- exact page cardinality;
- no duplicate DIFE public ID within/across pages;
- exact final unique-ID count.

The archive route performs no HTTP requests and therefore does not require a live collection policy review. The provenance still records that the universe came from a fixed staged archive.

## 3. Normalized bulk export

A lawful bulk export may arrive in a source-specific format.

The core application does **not** guess source column names.

Instead, a documented transformation first produces a canonical CSV with these columns:

\`\`\`text
dife_public_id
name
sector
location
upazila
district
division
licence_class
status
\`\`\`

The transformation itself must be documented in \`transform_note\`.

## 4. Independently declared total

A bulk CSV cannot certify its own completeness.

The import call therefore requires:

\`declared_total\`

This number must come from the source/export manifest, covering letter, source metadata, or another independently documented source total.

If:

\`\`\`text
declared_total = 89,127
CSV rows       = 89,126
\`\`\`

the import fails.

The code never substitutes \`len(csv_rows)\` for a missing external total.

## 5. Bulk provenance

A normalized bulk import retains privately:

- artifact path;
- SHA-256 hash;
- source URL/reference;
- retrieval timestamp;
- canonical field list;
- declared source total;
- transformation note.

The public product payload does not expose these private paths or manifests.

## 6. Common national universe

After successful import, both offline routes pass through the same final QC used by the live paginated route.

An eligible universe can therefore drive the same:

- district/division counts;
- source-native sector distribution;
- analytical sector families;
- status distribution;
- district × sector cells;
- location quotients;
- sector HHI;
- national establishment cluster context.

No special analytical rules exist merely because the source arrived offline.

## 7. Safe national dashboard contract

The national dashboard contract is:

\`schema_version = 1.0\`

It exposes:

- universe label and kind;
- source = DIFE;
- ingestion mode;
- completed timestamp;
- exact expected/unique-record counts;
- national summary;
- district/division tables;
- sector-family tables;
- district-sector cells;
- status distribution;
- source-native sector labels;
- disclosed formulas.

It does not expose:

- archive paths;
- raw payload paths;
- manifests;
- source URLs;
- internal universe/snapshot/observation IDs;
- hashes;
- private QC JSON.

Schema:

\`schemas/national_dashboard_v1.schema.json\`

## 8. Safe national registry feed

The national registry feed exposes one approved list-level row per establishment:

- public reference \`DIFE:<id>\`;
- name;
- list location;
- upazila/district/division;
- source-native sector label;
- analytical sector family;
- DIFE status;
- DIFE class;
- observation timestamp;
- source.

Internal numeric database IDs are not exported.

The intended distribution format is JSONL because a national registry may contain tens of thousands of rows.

Schema:

\`schemas/national_registry_row_v1.schema.json\`

## 9. Product files

The national product helpers can write:

\`\`\`text
national_dashboard.json
national_registry.jsonl
\`\`\`

These files are generated from the safe contract, not by serializing database rows.

Whether a generated product file should be public, private, customer-only or deployment-only remains a separate distribution decision.

## 10. Current status

The code can now ingest a national universe through a live paginated route, a fixed HTML archive, or a normalized lawful bulk export.

No real national DIFE snapshot has been loaded into the public repository.

The next development step is no longer ingestion plumbing. It is to build the first **national industrial geography product views** around the safe feed: district profiles, sector profiles, concentration tables and coverage-aware maps, while keeping synthetic/demo data until a real eligible universe is available.
