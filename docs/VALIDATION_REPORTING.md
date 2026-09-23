# Progressive validation reporting — v1.2

The 100-record detail stage is a **smoke-test gate**, not the end of validation.

The intended production sequence is:

```text
100 records
   ↓ pass
+400 records → cumulative 500
   ↓ pass
+1,500 records → cumulative 2,000
   ↓ pass
validation complete
```

Once collection is authorized, the progressive controller runs this sequence without a manual pause between successful gates. It stops only if a gate fails or a checkpoint remains locked.

## Why retain the 100-record gate?

A first checkpoint limits the cost of discovering a systemic problem such as:

- DIFE detail HTML changed;
- a filter/sample assumption was wrong;
- the parser is extracting the wrong labels;
- public URLs return unexpected pages;
- provenance is not being captured correctly;
- core fields are much less available than the feasibility audit suggested.

If none of those problems appears, there is no analytical reason to stop at 100.

## Automatic progression

The controller:

1. finds the smallest `READY` checkpoint;
2. runs only its newly unlocked tranche;
3. evaluates cumulative QC through that checkpoint;
4. creates the validation/anomaly report;
5. unlocks and immediately runs the next tranche when the gate passes;
6. stops at the first failure.

Thus a normal clean run executes **100 + 400 + 1,500 = 2,000** detail requests.

## List-to-detail consistency checks

Every cumulative checkpoint joins the detail observation back to the latest DIFE list-page observation used in candidate discovery.

The report flags:

- retrieval failure — CRITICAL;
- unresolved request — CRITICAL;
- structurally invalid parsed page — CRITICAL;
- district mismatch — HIGH;
- DIFE status mismatch — HIGH;
- industrial-sector mismatch — HIGH;
- class mismatch — MEDIUM;
- core-field incompleteness — MEDIUM;
- normalized name variation — INFO.

A mismatch is preserved as a source contradiction. The system does not overwrite one DIFE observation with the other.

## Why name variation is informational

List/detail names may differ because of English/Bangla presentation, punctuation, abbreviations or display conventions. A normalized name difference is therefore surfaced for review but is not automatically treated as an identity failure.

## Report contents

Each checkpoint report stores:

- total cumulative records;
- anomaly counts by type;
- anomaly counts by severity;
- sector-family breakdown;
- geography-group breakdown;
- parsed/valid/core-complete/failed counts by group.

Individual anomalies are stored separately with DIFE public ID, sequence number, list value, detail value and explanatory note.

## Versioning

Every report is append-only. Re-running a failed gate creates a new report rather than rewriting the prior result. The same applies to checkpoint QC decisions and collection-run audit records.

This preserves the full validation history.

## Live-data boundary

The controller does not bypass the source-access policy gate. It can advance automatically only when supplied with a collector instantiated under a documented `REVIEWED_ALLOWED` source policy.

Until then, the same pipeline can be exercised with staged pages and synthetic fixtures.
