# Development runbook

## Current public-code baseline

Run from the project root:

```bash
python -m pip install -e .[dev]
pytest
```

The current public baseline deliberately includes only synthetic fixtures. Real DIFE and enrichment-source data stay outside GitHub.

## Before any live 2,000-record validation

1. Re-verify DIFE/LIMA automation and reuse conditions.
2. Capture the live filter taxonomy rather than hard-coding internal sector IDs.
3. Discover public establishment IDs only from public list pages.
4. Freeze the validation sample before retrieving detail pages.
5. Start with a 100-record checkpoint and review parser/access errors before continuing.
6. Keep raw snapshots, working databases and exports outside this repository.

The detailed sampling plan is in `VALIDATION_2000_PLAN.md`.
