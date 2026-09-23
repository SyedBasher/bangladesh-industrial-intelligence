-- Offline national ingest provenance.

create table if not exists bii.national_ingest_sources (
  universe_id bigint primary key references bii.national_universe_runs(universe_id),
  ingest_mode text not null check(ingest_mode in (
    'LIVE_PAGINATED','STAGED_HTML_ARCHIVE','NORMALIZED_BULK_EXPORT'
  )),
  artifact_path text,
  artifact_sha256 text,
  manifest_json jsonb,
  imported_at timestamptz not null
);

create index if not exists national_ingest_mode_idx
  on bii.national_ingest_sources(ingest_mode, imported_at desc);
