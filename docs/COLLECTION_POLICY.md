# Live collection policy and private-run protocol — v1.1

The software can now perform a controlled private DIFE/LIMA detail run, but **live network collection is disabled by default**.

## Current source status

Feasibility work established that DIFE/LIMA exposes public establishment list, filtered-list and establishment-detail pages without an account. The public list is a living registry and its result counts and report timestamps change over time.

The repository does **not** treat public visibility as automatic permission for unattended bulk collection or commercial redistribution.

At the v1.1 audit point, a clear public bulk-reuse/automation licence had not been recorded. Therefore the built-in DIFE policy template remains:

`UNKNOWN`

and the live collector refuses to initialize from that template.

## Explicit policy states

- `UNKNOWN` — no live collection.
- `REVIEWED_RESTRICTED` — no live collection.
- `REVIEWED_ALLOWED` — collection may proceed only within the reviewed host/path/rate constraints.

An allowed policy must contain:

- source name;
- review timestamp;
- non-empty review note;
- HTTPS host allowlist;
- public path-prefix allowlist;
- maximum requests per minute;
- retry limit;
- timeout.

The decision is never inferred automatically from the existence of a public webpage.

## Collector behavior

The collector is intentionally conservative:

- single threaded;
- HTTP GET only;
- HTTPS only;
- exact host/path allowlist;
- explicit User-Agent;
- configurable request interval;
- limited retries;
- exponential backoff for transient failures;
- respects `Retry-After` when supplied;
- hard response-size cap;
- no sequential DIFE-ID probing.

The detail runner can request only records already authorized by the validation checkpoint engine.

## Private raw storage

Raw HTML is written below a caller-supplied private root, for example:

```text
raw/
  dife_detail/
    validation_2026_09/
      checkpoint_100/
        <dife_id>_<hash>.html
```

The repository `.gitignore` excludes `raw/`, database files, CSV, Parquet and spreadsheet exports.

The public repository must never contain these raw pages.

## Run audit

Before any live run begins, the private database records the exact access-policy review used for the run.

The run record then stores:

- validation label;
- checkpoint;
- linked policy-review record;
- start/completion timestamps;
- raw private directory;
- attempted/parsed/failed counts;
- final run state.

This makes later refreshes auditable. A run cannot merely inherit an undocumented assumption that collection was allowed.

## Checkpoint interaction

A collection run does not by itself unlock the next validation stage.

After collection, the existing QC engine still evaluates:

- request resolution;
- retrieval success;
- parser validity;
- provenance completeness;
- URL/DIFE-ID integrity;
- core-field completeness.

Only a passing QC decision unlocks the next tranche.

## Before the first real 100

The remaining operational action is to document the source-access review outside the public data layer. If review concludes that controlled automated retrieval is permitted, instantiate a `REVIEWED_ALLOWED` policy with the reviewed constraints and run only the READY 100-record tranche.

If permission remains unclear or restricted, use manually staged/publicly obtained pages for validation or seek clarification from DIFE rather than overriding the software gate.
