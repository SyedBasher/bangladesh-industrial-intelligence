# National snapshot execution and recovery — v2.1

The national DIFE analytical universe is deliberately separate from the live collector.

The v2.1 controller adds a bounded execution layer around the strict universe rules introduced in v2.0.

## 1. Source-access gate remains mandatory

The controller accepts a `PoliteHttpCollector` only when its reviewed source policy is for:

`DIFE/LIMA`

The collector itself still requires:

`decision = REVIEWED_ALLOWED`

A public webpage is not sufficient to enable live bulk collection.

No real national DIFE crawl is performed by this release.

## 2. Bounded page batches

A collection call processes at most a declared number of pages.

Default:

`max_pages = 50`

Example lifecycle:

```text
batch 1: pages 1–50
batch 2: pages 51–100
...
final batch
       ↓
strict final QC
       ↓
eligible national universe
```

Already staged pages are never fetched again during normal resume.

The batch size is an operational limit, not an analytical sampling rule. The final national universe still requires every planned page.

## 3. Seed-page expansion

A new universe begins with page 1 only.

After page 1 is staged, the source-reported total determines the exact complete page manifest.

If a prior process stops after staging page 1 but before expanding the manifest, the controller detects this state and expands the manifest before resuming.

## 4. Pre-membership integrity checks

A fetched page is checked before it is allowed into national-universe membership.

### Source-total drift

Every page after the seed must report exactly the same total as page 1.

A change such as:

```text
page 1 total = 89,127
page 87 total = 89,130
```

aborts the national universe.

The fetched page can remain in the private audit files, but its establishments are not added to the national membership.

### Page cardinality

Given the declared source total and page size, the number of parsed rows on each page must be exact.

For a 30-row page size, every non-final page must contain 30 parsed rows and the final page must contain the exact remainder.

A short/overfull page indicates source movement or parser/layout trouble and aborts the snapshot.

### Duplicate public IDs

The controller rejects:

- duplicate DIFE public IDs within one fetched page;
- a public ID already admitted on a prior page of the same national universe.

The bad page does not join the national membership.

## 5. Recoverable versus structural failure

Two classes of failure are treated differently.

### Recoverable failure

Examples:

- temporary network failure;
- HTTP retry exhaustion;
- parser failure after source markup changes.

The affected page is marked `FAILED`.

The national universe remains:

`RUNNING`

The failed page must be explicitly requeued with a reason before another collection attempt.

This prevents silent infinite retry loops.

### Structural integrity failure

Examples:

- source-total drift;
- duplicate public IDs across pages;
- impossible page cardinality.

The entire national universe becomes:

`FAILED`

It cannot be resumed.

A fresh national universe must be started.

## 6. Explicit failed-page requeue

A recoverable page can be reset with:

```python
store.requeue_failed_national_pages(
    universe_id,
    requeued_at=...,
    reason=...,
    pages=[...],
)
```

Every requeue is written to the recovery-event audit table.

The earlier page-attempt record is retained.

## 7. Fresh restart after integrity abort

A structurally invalid snapshot is never repaired by mixing old and new pages.

Instead:

```python
child_id = store.restart_national_universe_run(
    failed_universe_id,
    new_universe_label=...,
    started_at=...,
    reason=...,
)
```

The child starts again with only page 1 planned.

No page membership is copied from the failed parent.

The parent-child relationship and restart reason are retained in recovery events.

## 8. Page-attempt audit

Every attempted page records:

- collection-run ID;
- universe ID;
- page;
- URL;
- attempt and completion timestamps;
- outcome;
- HTTP status where available;
- collector attempt count;
- content hash;
- private raw-payload path;
- resulting source snapshot ID when staged;
- source-reported total;
- error message.

Outcomes are:

- `FETCHED_STAGED`
- `COLLECTION_FAILED`
- `PARSE_FAILED`
- `INTEGRITY_ABORT`

## 9. Private raw storage

Raw list pages are written under a private/gitignored tree such as:

```text
raw/
  dife_national/
    <universe-label>/
      universe_<id>/
        page_00001_<hash>.html
        page_00002_<hash>.html
        ...
```

The public repository contains the collector and methodology, not the national source extract.

## 10. Finalization

Automatic finalization occurs only when:

- no `PLANNED` pages remain;
- no `FAILED` pages remain;
- the universe is still `RUNNING`.

The v2.0 strict final QC then decides whether the universe becomes:

`COMPLETED + eligible_for_national_analysis = true`

or:

`FAILED + eligible_for_national_analysis = false`

## 11. Why this matters

A multi-thousand-page registry crawl can span enough time for records to be inserted, removed or reordered.

Restartability alone is not enough. Without drift and duplicate controls, a technically successful crawl can still produce a logically inconsistent cross-section.

The controller therefore prioritizes a defensible dated universe over completing a crawl at any cost.

## 12. Next step

After this controller is validated, the remaining prerequisite to a real national run is not more crawler code. It is the source-access decision.

Once that decision is documented as allowed, the controller can stage the real national snapshot privately in bounded batches.

If live bulk collection remains unavailable, the same national-universe machinery can ingest a lawful bulk export or manually staged page archive instead.
