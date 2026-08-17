# KU-BO Current Codex Status

Status date: 2026-08-17

Repository: `mohsamir7122/ku-bo`

## Active work

```text
main 59833bf73510b3aa3901f628cbf2c13c0d01cf79
  └── KU-BO-014 / Draft PR #18
      └── branch agent/humansoft-event-factor-panel-v1
          └── historical/current data-domain separation implementation in progress
          └── exact-head repository CI required before any readiness decision
```

## KU-BO-014 scope

The HUMANSOFT product is qualitative and disclosure-centered. It does not use the old factor registry or retrospective Accuracy layer. Its only user-facing questions are:

- did a rise begin before the official disclosure;
- did it begin immediately after or later after the disclosure;
- did it continue, fade, or fail to appear clearly;
- what source-backed public opinion existed before and after the disclosure.

## Data-domain separation

```text
HISTORICAL_DISCLOSURE_ARCHIVE       APPEND_ONLY
HISTORICAL_EVENT_MARKET_WINDOW      FROZEN
HISTORICAL_PUBLIC_OPINION_ARCHIVE   FROZEN_AS_OF_CAPTURE
RECENT_DAILY_MARKET_SERIES          ROLLING_CURRENT / CURRENT_CONTEXT_ONLY
LATEST_FINANCIAL_SNAPSHOT           REPLACE_BY_NEWER_SNAPSHOT / CURRENT_FINANCIAL_CONTEXT_ONLY
```

Recent daily market data and the latest financial snapshot are expressly excluded from historical disclosure-reaction computation. Updating either current dataset cannot modify a frozen historical event result.

## Evidence boundary

The repository can validate contracts and synthetic fixtures. It does not currently prove a lifetime-complete official HUMANSOFT disclosure archive, a complete Corporate-Actions ledger, authoritative historical Total Return data, or Point-in-Time market/sector Benchmark history. Missing evidence must remain fail-closed.

## Validation checkpoint

- separated-domain focused suite: pending publication on exact branch head;
- complete repository suite: pending;
- exact-head GitHub Actions on Python 3.11 through 3.14: pending;
- merge: not authorized.
