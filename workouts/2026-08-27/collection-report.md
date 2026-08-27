# Collection Report

```text
STATUS: BLOCKED_AT_OFFICIAL_SOURCE_ACCESS
VERIFIED_COMPANIES: 0
VERIFIED_PRICE_SERIES: 0
ADMITTED_DISCLOSURES: 0
ADMITTED_NEWS_ITEMS: 0
ADMITTED_CORPORATE_ACTIONS: 0
FAILED_SOURCE_ATTEMPTS: 2
```

PRE-FLIGHT and source-policy inspection do not count as market-data collection.
No company file, market row, disclosure, news item, or corporate action has been
claimed. Collection begins only after the Kuwait universe and source-admission
contracts are validated. Missing data will remain explicitly missing.

The Stage 1 reconciliation dry run used `SYNTHETIC_FIXTURE` only. Its single
synthetic expected cell and observation are excluded from every company/event
count above.

The Stage 2 dossier dry run used one explicitly synthetic issuer/security and 21
synthetic fields. They validate software structure only and are likewise excluded
from `VERIFIED_COMPANIES`, price-series, disclosure, and action counts.

Two real capability probes were attempted after the source contracts were
implemented: `kcc_maqasa_official` and `boursa_reports_archive`. Both ended
`ROBOTS_POLICY_UNAVAILABLE`, with no readable artifact. They increase only the
failed-attempt count; every market-data count remains zero.

Stage 4 accessed official public schedule/holiday pages solely to verify the
automation calendar. Those administrative facts are not company or market-data
collection and do not change any count above. All seven schedule dry runs kept
collection disabled.

## Rights-aware 90-day attempt audit

The initial package for 2026-05-30 through 2026-08-27 is deliberately named
`INCOMPLETE_RIGHTS_AWARE_RESEARCH_CONTEXT`. It is an attempt/coverage ledger,
not a completed collection or training dataset.

| Measure | Actual count |
| --- | ---: |
| Trusted source groups in denominator | 11 |
| Planned source/date shards | 990 |
| Source attempts | 2 |
| Blocked sources | 2 |
| Blocked-before-fetch shards | 180 |
| Unattempted shards | 810 |
| Completed shards | 0 |
| Readable raw artifacts | 0 |
| Real observations | 0 |
| Unique events | 0 |
| Research-context rows | 0 |
| Training candidates | 0 |

The attempted sources were `boursa_reports_archive` and
`kcc_maqasa_official`; both remain `BLOCKED_ROBOTS` with terminal code
`ROBOTS_POLICY_UNAVAILABLE`. No bypass or substitute data was used.
