# Investing USER_EXPORT input

This directory is documentation-only. Do not commit real provider exports here.
Use `prepare-price-collection-workspace` to create a run-scoped directory under
`runtime/`, then place the authorized CSV files and the reviewed collection
manifest there.

The seed mapping currently expects:

- `NBK.csv` — security code `101`, ISIN `KW0EQ0100010`
- `KFH.csv` — security code `108`, ISIN `KW0EQ0100085`
- `MABANEE.csv` — security code `413`, ISIN `KW0EQ0400725`
- `ZAIN.csv` — security code `605`, ISIN `KW0EQ0601058`
- `HUMANSOFT.csv` — security code `623`, ISIN `KW0EQ0601694`

Each CSV must use this exact header and newest-first order:

```csv
Date,Price,Open,High,Low,Vol.,Change %
"Aug 06, 2026",101.000,100.000,102.000,99.000,1.25M,+1.00%
"Aug 05, 2026",100.000,99.000,101.000,98.000,1.00M,0.00%
```

The importer also requires `manifests/price_collection_manifest.csv` from the
generated workspace. Every accepted row must contain a matching SHA-256,
identity, URL, date range, row count, `RAW` or `ADJUSTED` price basis, unit,
download time, and `review_status=ACCEPTED`.

See:

- `docs/PRICE_FILE_COLLECTION_POLICY_AR.md`
- `docs/ALL_MARKET_PRICE_COLLECTION_RUNBOOK_AR.md`
- `examples/price_file_collection_manifest_template.csv`

Successful import means `PRICE_IMPORT_READY_ONLY`. It does not mean that an
official identity artifact, corporate actions, calendar, benchmark, or a real
backtest is ready.
