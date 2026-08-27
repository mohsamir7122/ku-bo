# Rights-Aware 90-Day Backfill Report

Recorded: 2026-08-27T10:02:25Z

```text
PACKAGE: INCOMPLETE_RIGHTS_AWARE_RESEARCH_CONTEXT
MARKET: KUWAIT
WINDOW: 2026-05-30..2026-08-27 (inclusive, 90 days)
AUDIT_CODE_SHA: e9d1a7fde8fde98d131c61c8aef97eb0619b6d0d
WORKFLOW_CODE_SHA: 85a9068d05b9c015d2044f78d0bdc9b1558d569e
MANIFEST_DIGEST: d5c07df65a7b80ed8a332b3e472eadfd6a7633a6718bff07e498b0ba14a96069
PRODUCTION_STATUS: BLOCKED_CHECKPOINT_STORE
RESEARCH_NETWORK: SOFTWARE_OPERATIONAL_ABSTAIN
STRICT_FORECAST: LOCKED
```

The immutable private runtime package was built outside Git from the two
existing real source-access receipts and then reopened independently. Its
private locator is intentionally not persisted in the repository.

## Actual evidence counts

| Measure | Count |
| --- | ---: |
| Trusted source independence groups | 11 |
| Planned source/date shards | 990 |
| Attempts | 2 |
| Blocked sources | 2 |
| Blocked-before-fetch shards | 180 |
| Unattempted shards | 810 |
| Completed shards | 0 |
| Raw artifacts | 0 |
| Observations | 0 |
| Provenance records | 0 |
| Unique events | 0 |
| Research-context records | 0 |
| Training candidates | 0 |
| Contradictions | 0 |

Both `boursa_reports_archive` and `kcc_maqasa_official` are
`BLOCKED_ROBOTS / ROBOTS_POLICY_UNAVAILABLE`. A blocked attempt is not a
successful collection. No source bytes, company row, event, price, prediction,
or training record was created.

## Gates

- Receipt plan/probe hashes and trusted source roles are reopened and verified.
- Path traversal, symlinks, artifact mutation, overwrite, and temporal leakage
  are rejected.
- Every JSONL record requires explicit admission and immutable provenance.
- Production scheduling exits nonzero before source access because no reviewed
  durable checkpoint store exists.
- Dataset release, challenger training, temporal validation, locked Blind Test,
  prospective shadow, and promotion are not authorized.

## Validation

- Rights-aware package tests: 18/18 passed.
- Combined recovery/schedule/lease/priority/workflow tests: 106/106 passed.
- Schema validation, YAML parse, Actionlint 1.7.12, compile, diff check, and
  Secret Guard passed.
- CI `33059176971` passed exact package head `e9d1a7f`; workflow-head CI
  `33060045908` passed `85a9068` on Python 3.11 through 3.14.
- Final local reruns passed the 106-test combined gate, 102/102 source/research/
  control/secret-unit tests, and standalone Secret Guard.

Schedules are declarations only and are not active until reviewed changes reach
the default branch through an authorized merge.
